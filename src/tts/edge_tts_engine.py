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

    @staticmethod
    def validate_text_for_tts(text: Optional[str]) -> bool:
        """
        Validates whether the text can be processed by Edge-TTS.
        Ensures the text is not empty, is not None, is not only whitespace,
        and contains at least one alphanumeric character (so Edge-TTS doesn't fail).
        """
        if not text:
            return False
        stripped = text.strip()
        if not stripped:
            return False
        # If there are no alphanumeric characters (e.g. only "...", "!!!"), Edge-TTS will fail
        return any(char.isalnum() for char in stripped)

    async def _synthesize_single_segment(
        self,
        idx: int,
        text: str,
        output_file: Path,
        voice: str,
        semaphore: asyncio.Semaphore
    ) -> bool:
        """
        Synthesizes a single text string to an audio file safely using a semaphore to limit concurrency.
        Retries up to 3 times per voice, and falls back to other valid English voices if the primary fails.
        Returns True on success, False on failure.
        """
        async with semaphore:
            # 1. Determine list of voices to try: primary first, followed by fallbacks
            fallback_voices = ["en-US-AriaNeural", "en-US-JennyNeural", "en-US-GuyNeural"]
            voices_to_try = [voice]
            for fb in fallback_voices:
                if fb != voice:
                    voices_to_try.append(fb)

            # 2. Detailed segment logging (Requirement 6)
            logger.info(
                f"TTS Segment {idx}: voice={voice}, length={len(text)}, preview='{text[:50]}'"
            )

            # 3. Attempt synthesis with retries and fallbacks (Requirements 8 & 9)
            for v in voices_to_try:
                for attempt in range(1, 4):
                    try:
                        communicate = edge_tts.Communicate(text=text, voice=v)
                        await communicate.save(str(output_file))
                        logger.info(f"Successfully generated TTS for Segment {idx} using voice '{v}' on attempt {attempt}")
                        return True
                    except Exception as e:
                        logger.warning(
                            f"Edge-TTS synthesis attempt {attempt} failed for Segment {idx} using voice '{v}': {e}"
                        )
                        if attempt < 3:
                            await asyncio.sleep(attempt * 0.5)
                logger.warning(f"Voice '{v}' failed to synthesize Segment {idx} after 3 attempts. Trying next fallback.")
            
            logger.error(f"All voices failed to synthesize Segment {idx}. Skipping segment safely.")
            return False

    async def _synthesize_batch(
        self,
        segments: List[Dict[str, Any]],
        voice: str,
        concurrency_limit: int = 5
    ) -> List[Path]:
        """
        Runs batch synthesis of multiple segments concurrently and fault-tolerantly.
        Does not fail the entire batch if a single segment fails.
        """
        semaphore = asyncio.Semaphore(concurrency_limit)
        tasks = []
        output_paths = [None] * len(segments)
        
        for idx, seg in enumerate(segments):
            text = seg.get("translated_text", "").strip()
            
            # Validate text before calling Edge-TTS
            if not self.validate_text_for_tts(text):
                logger.info(f"Segment {idx}: Text is empty, only whitespace/punctuation, or invalid. Skipping.")
                continue
                
            out_file = self.output_directory / f"segment_{idx:04d}.mp3"
            
            # Helper to wrap the task and set the output path upon success
            async def run_task(i=idx, txt=text, f=out_file):
                try:
                    success = await self._synthesize_single_segment(
                        idx=i,
                        text=txt,
                        output_file=f,
                        voice=voice,
                        semaphore=semaphore
                    )
                    if success:
                        output_paths[i] = f
                except Exception as e:
                    logger.error(f"Unexpected error in TTS task for Segment {i}: {e}")

            tasks.append(run_task())
            
        if tasks:
            # Fault-tolerant asyncio execution: exceptions do not halt other tasks
            await asyncio.gather(*tasks, return_exceptions=True)
            
        return output_paths

    def generate_dubbed_segments(
        self,
        segments: List[Dict[str, Any]],
        voice: Optional[str] = None
    ) -> List[Path]:
        """
        Synchronously wrapped method to generate speech for all segments concurrently.
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
                
            logger.info("Voice synthesis batch processing completed.")
            return audio_paths
            
        except Exception as e:
            logger.error(f"TTS batch synthesis critical failure: {e}")
            raise TTSEngineError(f"TTS generation failed: {e}") from e