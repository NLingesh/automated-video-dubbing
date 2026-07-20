import os
import time
from pathlib import Path
import streamlit as st

# Configure Streamlit page
st.set_page_config(
    page_title="AI Video Dubbing Studio",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium CSS Injection
st.markdown(
    """
    <style>
    /* Dark glassmorphic container styling */
    .stApp {
        background-color: #0A0E17;
    }
    
    div[data-testid="stVerticalBlock"] > div:has(div.element-container) {
        background: rgba(19, 28, 46, 0.4);
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 15px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Title Styling */
    .studio-title {
        font-size: 3rem !important;
        font-weight: 800 !important;
        background: linear-gradient(90deg, #FF3366 0%, #FF6633 50%, #FFCC33 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 10px;
        text-shadow: 0 4px 20px rgba(255, 51, 102, 0.15);
    }
    
    .studio-subtitle {
        color: #9CA3AF;
        font-size: 1.15rem;
        margin-bottom: 30px;
    }
    
    /* Code logs styling */
    .stCodeBlock {
        background-color: #0D1117 !important;
        border: 1px solid #1F2937 !important;
        border-radius: 8px !important;
    }
    
    /* Styled buttons */
    div.stButton > button {
        background: linear-gradient(135deg, #FF3366 0%, #FF6633 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        padding: 10px 24px !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 15px rgba(255, 51, 102, 0.3) !important;
    }
    
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(255, 51, 102, 0.4) !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Header Section
st.markdown("<h1 class='studio-title'>🎙️ AI Video Dubbing Studio</h1>", unsafe_allow_html=True)
st.markdown(
    "<p class='studio-subtitle'>Transform any YouTube video into a fully dubbed masterpiece using advanced AI transcription, translation, and high-fidelity speech synthesis.</p>",
    unsafe_allow_html=True
)

# Configuration mapping for languages and voices
LANGUAGE_VOICES = {
    "English (US)": {"code": "en", "voice": "en-US-GuyNeural"},
    "English (US, Female)": {"code": "en", "voice": "en-US-AriaNeural"},
    "English (UK)": {"code": "en", "voice": "en-GB-SoniaNeural"},
    "Spanish (Spain)": {"code": "es", "voice": "es-ES-AlvaroNeural"},
    "French (France)": {"code": "fr", "voice": "fr-FR-HenriNeural"},
    "German (Germany)": {"code": "de", "voice": "de-DE-ConradNeural"},
    "Hindi (India)": {"code": "hi", "voice": "hi-IN-MadhurNeural"},
    "Telugu (India)": {"code": "te", "voice": "te-IN-MohanNeural"},
}

col1, col2 = st.columns([1, 1.2], gap="large")

with col1:
    st.subheader("🛠️ Production Settings")
    
    # URL Input
    youtube_url = st.text_input(
        "YouTube Video URL",
        placeholder="https://www.youtube.com/watch?v=...",
        help="Paste a link to any public YouTube video."
    )
    
    # Whisper Model Selection
    whisper_model = st.selectbox(
        "Whisper Speech-to-Text Model",
        options=["tiny", "base", "small", "medium", "large"],
        index=1,
        help="Base is fast and lightweight. Small/Medium offer better accuracy but require more compute resources."
    )
    
    # Target Language
    selected_lang_name = st.selectbox(
        "Output Target Language & Voice",
        options=list(LANGUAGE_VOICES.keys()),
        index=0,
        help="Select the language and specific AI voice model for the dubbing output."
    )
    
    lang_info = LANGUAGE_VOICES[selected_lang_name]
    target_code = lang_info["code"]
    voice_name = lang_info["voice"]
    
    st.info(f"Selected Config: **{target_code.upper()}** via voice **{voice_name}**")
    
    start_dubbing = st.button("🔥 Start Dubbing Process")

with col2:
    st.subheader("📺 Processing Dashboard")
    
    # Placeholders for progress bar, status, logs, preview, and download buttons
    status_placeholder = st.empty()
    progress_placeholder = st.empty()
    logs_title_placeholder = st.empty()
    logs_placeholder = st.empty()
    preview_placeholder = st.empty()
    download_col_1, download_col_2, download_col_3 = st.columns(3)
    
    # Helper to load and read the latest log output
    def get_latest_logs(tail_lines=35) -> str:
        log_path = Path("output/logs/dubbing_pipeline.log")
        if log_path.exists():
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    return "".join(lines[-tail_lines:])
            except Exception:
                return "Failed to read logs..."
        return "Waiting for pipeline logs to initialize..."

    # Callback update function
    def update_streamlit_ui(percent: int, message: str):
        progress_placeholder.progress(percent)
        status_placeholder.markdown(f"**Current Status:** {message}")
        logs_title_placeholder.caption("Live Pipeline Logs:")
        logs_placeholder.code(get_latest_logs(), language="text")

    # Initial state
    status_placeholder.info("Ready. Enter a YouTube URL and click 'Start' to begin the dubbing pipeline.")
    
    if start_dubbing:
        # Validate URL
        youtube_url = youtube_url.strip()
        if not youtube_url:
            st.error("YouTube URL is required!")
        elif not any(domain in youtube_url for domain in ["youtube.com/watch", "youtu.be/", "youtube.com/v/", "youtube.com/embed/", "youtube.com/shorts/"]):
            st.error("Invalid YouTube URL. Please enter a valid YouTube link.")
        else:
            status_placeholder.warning("Starting pipeline execution...")
            progress_placeholder.progress(0)
            
            # Import pipeline dynamically
            from src.pipeline import VideoDubbingPipeline
            
            try:
                pipeline = VideoDubbingPipeline()
                
                # Execute pipeline with parameters
                final_video_path = pipeline.run(
                    url=youtube_url,
                    whisper_model=whisper_model,
                    voice=voice_name,
                    target_lang=target_code,
                    progress_callback=update_streamlit_ui
                )
                
                if final_video_path and final_video_path.exists():
                    status_placeholder.success("🎉 Video Dubbing Process Completed Successfully!")
                    progress_placeholder.progress(100)
                    
                    # Display Video Preview
                    preview_placeholder.video(str(final_video_path))
                    
                    # Setup download buttons
                    srt_path = Path("output/subtitles/video.srt")
                    report_path = Path("output/report.json")
                    
                    # Download Video
                    with download_col_1:
                        with open(final_video_path, "rb") as f:
                            st.download_button(
                                label="📥 Dubbed Video",
                                data=f,
                                file_name=final_video_path.name,
                                mime="video/mp4",
                                key="btn_download_video",
                                use_container_width=True
                            )
                            
                    # Download Subtitles
                    with download_col_2:
                        if srt_path.exists():
                            with open(srt_path, "rb") as f:
                                st.download_button(
                                    label="📥 SRT Subtitles",
                                    data=f,
                                    file_name=srt_path.name,
                                    mime="text/plain",
                                    key="btn_download_subtitles",
                                    use_container_width=True
                                )
                        else:
                            st.caption("Subtitles not found")
                            
                    # Download Execution Report
                    with download_col_3:
                        if report_path.exists():
                            with open(report_path, "rb") as f:
                                st.download_button(
                                    label="📥 Report JSON",
                                    data=f,
                                    file_name="report.json",
                                    mime="application/json",
                                    key="btn_download_report",
                                    use_container_width=True
                                )
                        else:
                            st.caption("Report not found")
                            
                else:
                    status_placeholder.error("Pipeline failed to produce the final dubbed video.")
                    st.error("Please inspect the log files for troubleshooting details.")
            except Exception as e:
                status_placeholder.error(f"Critical execution failure: {e}")
                st.exception(e)
