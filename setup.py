from setuptools import setup
setup(
    name="video-auto-pipeline",
    version="2.0.0",
    description="One-shot talking-head video editor. Transcribe, LLM analyze, smart cut, HyperFrames render.",
    py_modules=["pipeline", "hf_composition"],
    entry_points={
        "console_scripts": [
            "video-pipeline=pipeline:main",
        ],
    },
    install_requires=[
        "faster-whisper>=1.1.0",
        "requests>=2.31.0",
    ],
    python_requires=">=3.10",
)
