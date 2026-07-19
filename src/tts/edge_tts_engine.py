import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import edge_tts
from src.utils.logger import setup_logger

logger = setup_logger("edge_tts_engine")


class TTSEngineError(Exception):
    """Custom exception for TTS failures."""
    pass


class EdgeTTSEngine:
    """
    Converts English text segments into speech using Edge-TTS asynchronously.
    Supports voice selection, concurrency control using semaphores, and rate-limiting resilience.
    """

    def __init__(self, output_directory: Path, voice: str = "en-US-GuyNeural"):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.voice = voice

    async def _synthesize_single_segment(
        self,
        text: str,
        output_file: Path,
        voice: str,
        semaphore: asyncio.Semaphore
    ) -> None:
        """
        Synthesizes a single text string to an audio file safely using a semaphore to limit concurrency.
        """
        async with semaphore:
            for attempt in range(1, 4):
                try:
                    communicate = edge_tts.Communicate(text=text, voice=voice)
                    await communicate.save(str(output_file))
                    return
                except Exception as e:
                    logger.warning(
                        f"Edge-TTS synthesis attempt {attempt} failed for '{text[:20]}...': {e}"
                    )
                    if attempt == 3:
                        raise TTSEngineError(f"Failed to generate TTS after 3 attempts: {e}") from e
                    await asyncio.sleep(attempt * 0.5)

    async def _synthesize_batch(
        self,
        segments: List[Dict[str, Any]],
        voice: str,
        concurrency_limit: int = 5
    ) -> List[Path]:
        """
        Runs batch synthesis of multiple segments concurrently.
        """
        semaphore = asyncio.Semaphore(concurrency_limit)
        tasks = []
        output_paths = []
        
        for idx, seg in enumerate(segments):
            text = seg.get("translated_text", "").strip()
            
            # If segment has no text, skip synthesis tasks
            if not text:
                output_paths.append(None)
                continue
                
            out_file = self.output_directory / f"segment_{idx:04d}.mp3"
            output_paths.append(out_file)
            
            tasks.append(
                self._synthesize_single_segment(
                    text=text,
                    output_file=out_file,
                    voice=voice,
                    semaphore=semaphore
                )
            )
            
        await asyncio.gather(*tasks)
        return output_paths

    def generate_dubbed_segments(
        self,
        segments: List[Dict[str, Any]],
        voice: Optional[str] = None
    ) -> List[Path]:
        """
        Synchronously wrapped method to generate speech for all segments concurrently.
        Modifies segments by adding 'audio_path' key.
        """
        target_voice = voice or self.voice
        logger.info(f"Generating TTS for {len(segments)} segments using voice: {target_voice}")
        
        if not segments:
            return []

        try:
            # Set up asyncio event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                audio_paths = loop.run_until_complete(
                    self._synthesize_batch(segments, target_voice)
                )
            finally:
                loop.close()
                
            logger.info("Voice synthesis completed for all segments.")
            return audio_paths
            
        except Exception as e:
            logger.error(f"TTS batch synthesis failed: {e}")
            raise TTSEngineError(f"TTS generation failed: {e}") from e