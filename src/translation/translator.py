import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional
from googletrans import Translator
from src.utils.logger import setup_logger

logger = setup_logger("translator")


class TranslationError(Exception):
    """Custom exception for translation failures."""
    pass


class BaseTranslator(ABC):
    """
    Abstract Base Class defining the translation engine interface.
    This allows swapping between Google Translate, IndicTrans2, DeepL, etc.
    """

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translates a single string of text.
        """
        pass

    @abstractmethod
    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        """
        Translates a batch of texts for performance and API quota optimization.
        """
        pass


class GoogleTranslatorEngine(BaseTranslator):
    """
    Google Translate implementation using googletrans==4.0.0rc1.
    """

    def __init__(self, retries: int = 3, delay: float = 1.0):
        self.translator = Translator()
        self.retries = retries
        self.delay = delay

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        if not text.strip():
            return ""
            
        for attempt in range(1, self.retries + 1):
            try:
                result = self.translator.translate(text, src=source_lang, dest=target_lang)
                return result.text
            except Exception as e:
                logger.warning(f"Google Translate single translation attempt {attempt} failed: {e}")
                if attempt == self.retries:
                    raise TranslationError(f"Google Translate failed after {self.retries} attempts: {e}") from e
                time.sleep(self.delay * attempt)
        return ""

    def translate_batch(self, texts: List[str], source_lang: str, target_lang: str) -> List[str]:
        cleaned_texts = [text.strip() for text in texts]
        if not cleaned_texts:
            return []
            
        # Filter empty strings but keep track of indices to reconstruct list later
        non_empty_texts = [text for text in cleaned_texts if text]
        if not non_empty_texts:
            return [""] * len(texts)

        try:
            results = []
            for text in non_empty_texts:
                res = self.translate(text, source_lang=source_lang, target_lang=target_lang)
                results.append(res)
                # Small safety delay to prevent Google Translate rate limiting
                time.sleep(0.1)
            
            # Reconstruct full list (matching original indices)
            final_translations = []
            idx = 0
            for text in cleaned_texts:
                if text:
                    final_translations.append(results[idx])
                    idx += 1
                else:
                    final_translations.append("")
                    
            return final_translations
        except Exception as e:
            logger.error(f"Translation batch loop failed: {e}")
            raise TranslationError(f"Batch translation loop failed: {e}") from e



class VideoTranslator:
    """
    Coordinates translation of transcripts and individual speech segments.
    """

    def __init__(self, output_directory: Path, engine: Optional[BaseTranslator] = None):
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        # Default to Google Translator Engine if none is specified
        self.engine = engine or GoogleTranslatorEngine()

    def translate_segments(
        self,
        segments: List[Dict[str, Any]],
        source_lang: str,
        target_lang: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Translates a list of speech segments into the target language.
        Modifies segments by adding a 'translated_text' field.
        """
        logger.info(f"Translating {len(segments)} segments from '{source_lang}' to '{target_lang}'")
        
        if not segments:
            return []

        # Extract texts for batch translation
        texts_to_translate = [seg.get("text", "") for seg in segments]
        
        try:
            translated_texts = self.engine.translate_batch(
                texts_to_translate,
                source_lang=source_lang,
                target_lang=target_lang
            )
            
            # Update segments with translations
            translated_segments = []
            for seg, trans_text in zip(segments, translated_texts):
                updated_seg = seg.copy()
                updated_seg["translated_text"] = trans_text.strip()
                translated_segments.append(updated_seg)
                
            # Save the complete translated text to output directory
            full_translated_text = "\n".join(
                [seg["translated_text"] for seg in translated_segments if seg["translated_text"]]
            )
            output_file = self.output_directory / "translated_text.txt"
            output_file.write_text(full_translated_text, encoding="utf-8")
            
            logger.info(f"Segment translation complete. Saved full text to: {output_file.name}")
            return translated_segments
            
        except Exception as e:
            logger.error(f"Failed to translate segments: {e}")
            raise TranslationError(f"Segment translation failed: {e}") from e