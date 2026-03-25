"""
test_e2e.py - End-to-end workflow test for RAGAI ecosystem.

Runs the full pipeline:
  topic → story → images → voice → video assembly → thumbnail → test report

Target: ~3 minute video (6 scenes)
Output: test/ folder
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

TEST_DIR = Path("test")
TEST_DIR.mkdir(exist_ok=True)

LOG_FILE = TEST_DIR / "test_e2e.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
logger = logging.getLogger("test_e2e")

# ---------------------------------------------------------------------------
# Test config
# ---------------------------------------------------------------------------

TEST_TOPIC    = "Village girl becomes IAS officer through hard work and sacrifice"
TEST_LANGUAGE = "hi"
TEST_STYLE    = "AUTO"
TEST_AUDIENCE = "family"
SCENE_COUNT   = 6       # ~30s per scene = ~3 min total
TARGET_MINS   = 3.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    bar = "=" * 60
    logger.info("\n%s\n  %s\n%s", bar, title, bar)


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    if condition:
        logger.info(msg)
    else:
        logger.error(msg)
    return condition


# ---------------------------------------------------------------------------
# Stage 1: Config + API keys
# ---------------------------------------------------------------------------

def test_config():
    section("Stage 1: Config + API Keys")
    from config import load_config
    cfg = load_config()
    ok = True
    ok &= check("GROQ_API_KEY present", bool(cfg.groq_api_key))
    ok &= check("LEONARDO_API_KEY present", bool(cfg.leonardo_api_key))
    return cfg, ok


# ---------------------------------------------------------------------------
# Stage 2: Topic quality scoring
# ---------------------------------------------------------------------------

def test_topic_quality():
    section("Stage 2: Topic Quality Engine")
    from topic_quality_engine import TopicQualityEngine
    engine = TopicQualityEngine()
    result = engine.score(TEST_TOPIC)
    logger.info("Score result: %s", json.dumps(result, ensure_ascii=False, indent=2))
    ok = check("Composite score >= 2.0", result["score"] >= 2.0,
               f"score={result['score']}")
    return result, ok


# ---------------------------------------------------------------------------
# Stage 3: Engagement prediction
# ---------------------------------------------------------------------------

def test_engagement(topic_score: float):
    section("Stage 3: Engagement Predictor")
    from engagement_predictor import EngagementPredictor
    predictor = EngagementPredictor()
    result = predictor.predict(
        topic=TEST_TOPIC,
        title="गाँव की लड़की बनी IAS अफसर | सच्ची कहानी",
        topic_score=topic_score,
    )
    logger.info("Prediction: %s", json.dumps(result, ensure_ascii=False, indent=2))
    ok = check("should_generate = True", result["should_generate"],
               f"CTR={result['predicted_ctr']}% watch={result['predicted_watch_minutes']}min")
    return ok


# ---------------------------------------------------------------------------
# Stage 4: Narrative structure selection
# ---------------------------------------------------------------------------

def test_narrative():
    section("Stage 4: Narrative Variation Engine")
    from narrative_variation_engine import NarrativeVariationEngine
    engine = NarrativeVariationEngine()
    structure = engine.pick_structure()
    suffix = engine.build_prompt_suffix(TEST_TOPIC, language=TEST_LANGUAGE)
    ok = check("Structure selected", bool(structure.code), f"code={structure.code} name={structure.name}")
    ok &= check("Prompt suffix non-empty", len(suffix) > 50)
    logger.info("Structure: %s — %s", structure.code, structure.name)
    return structure, ok


# ---------------------------------------------------------------------------
# Stage 5: Content variation plan
# ---------------------------------------------------------------------------

def test_content_variation():
    section("Stage 5: Content Variation Engine")
    from content_variation_engine import ContentVariationEngine
    engine = ContentVariationEngine()
    plan = engine.pick_plan_for_topic(TEST_TOPIC)
    durations = engine.scene_durations(SCENE_COUNT, plan.pacing)
    ok = check("Plan generated", bool(plan.voice_style and plan.music_mood and plan.pacing))
    ok &= check("Scene durations count", len(durations) == SCENE_COUNT,
                f"got {len(durations)}")
    ok &= check("Durations are positive",
                all(d > 0 for d in durations),
                f"total={sum(durations):.1f}s (pacing profile range)")
    logger.info("Plan: %s", plan.summary())
    logger.info("Durations: %s", durations)
    return plan, ok


# ---------------------------------------------------------------------------
# Stage 6: Story archive duplicate check
# ---------------------------------------------------------------------------

def test_story_archive():
    section("Stage 6: Story Archive")
    from story_archive import StoryArchive
    archive = StoryArchive(db_path=TEST_DIR / "story_archive_test.db")
    is_dup = archive.check_duplicate_topic(TEST_TOPIC)
    ok = check("Duplicate check runs without error", True)
    logger.info("Is duplicate: %s", is_dup)
    return archive, ok


# ---------------------------------------------------------------------------
# Stage 7: Full pipeline (story → images → voice → video)
# ---------------------------------------------------------------------------

def test_pipeline(app_config):
    section("Stage 7: Full Pipeline — Story + Images + Voice + Video")
    from models import (
        Audience, Language, VideoFormat, VisualStyle,
        QualityPreset, InputMode, PipelineConfig
    )
    from pipeline import Pipeline

    config = PipelineConfig(
        topic=TEST_TOPIC,
        script_file=None,
        audience=Audience(TEST_AUDIENCE),
        language=Language(TEST_LANGUAGE),
        style=VisualStyle(TEST_STYLE),
        format=VideoFormat.LANDSCAPE,
        character_names={},
        output_dir=TEST_DIR,
        use_edge_tts=app_config.use_edge_tts,
        groq_api_key=app_config.groq_api_key,
        leonardo_api_key=app_config.leonardo_api_key,
        scene_count=SCENE_COUNT,
        quality=QualityPreset.DRAFT,       # 720p — fastest encode, avoids pipe buffer issues
        target_duration_minutes=TARGET_MINS,
    )

    last_stage = "init"
    def progress(stage, scene, total):
        nonlocal last_stage
        last_stage = stage
        print(f"\r  [{stage}] scene {scene}/{total}   ", end="", flush=True)

    t0 = time.time()
    try:
        result = Pipeline(config, progress).run()
        print()
        elapsed = time.time() - t0
        ok = True
        ok &= check("Video file exists", result.output_path.exists(),
                    str(result.output_path))
        ok &= check("Video file > 500KB",
                    result.output_path.stat().st_size > 500_000,
                    f"{result.output_path.stat().st_size // 1024}KB")
        ok &= check("Scene count correct", len(result.scenes) == SCENE_COUNT,
                    f"got {len(result.scenes)}")
        logger.info("Pipeline elapsed: %.1fs", elapsed)
        logger.info("Output: %s", result.output_path)
        return result, ok
    except Exception as exc:
        print()
        logger.error("Pipeline failed at stage '%s': %s", last_stage, exc, exc_info=True)
        return None, False


# ---------------------------------------------------------------------------
# Stage 8: Thumbnail A/B variants
# ---------------------------------------------------------------------------

def test_thumbnails(pipeline_result):
    section("Stage 8: Thumbnail A/B Testing")
    if not pipeline_result:
        logger.warning("Skipping — no pipeline result")
        return False

    from thumbnail_ab_tester import ThumbnailABTester
    tester = ThumbnailABTester(results_file=TEST_DIR / "ab_test_results.json")
    variants = tester.generate_variants(
        video_path=pipeline_result.output_path,
        title=TEST_TOPIC,
        output_dir=TEST_DIR,
        video_id="test_e2e_001",
    )
    ok = check("At least 1 thumbnail variant generated", len(variants) >= 1,
               f"variants={list(variants.keys())}")
    for layout, path in variants.items():
        ok &= check(f"Thumbnail {layout} exists", path.exists(), str(path))
    return ok


# ---------------------------------------------------------------------------
# Stage 9: Story archive save
# ---------------------------------------------------------------------------

def test_archive_save(archive, pipeline_result):
    section("Stage 9: Story Archive Save")
    if not pipeline_result:
        logger.warning("Skipping — no pipeline result")
        return False

    sid = archive.save_story(
        topic=TEST_TOPIC,
        summary=f"Test run — {SCENE_COUNT} scenes",
        language=TEST_LANGUAGE,
        style=TEST_STYLE,
        video_id="test_e2e_001",
        word_count=sum(len(s.narration.split()) for s in pipeline_result.scenes),
    )
    ok = check("Story saved to archive", bool(sid), f"id={sid}")
    is_dup = archive.check_duplicate_topic(TEST_TOPIC)
    ok &= check("Duplicate now detected after save", is_dup)
    stats = archive.stats()
    logger.info("Archive stats: %s", stats)
    return ok


# ---------------------------------------------------------------------------
# Stage 10: Video duration verification
# ---------------------------------------------------------------------------

def test_video_duration(pipeline_result):
    section("Stage 10: Video Duration Verification")
    if not pipeline_result:
        logger.warning("Skipping — no pipeline result")
        return False

    import subprocess, shutil
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        local = Path("ffmpeg-8.1-essentials_build") / "bin" / "ffprobe.exe"
        ffprobe = str(local) if local.exists() else None

    if not ffprobe:
        logger.warning("ffprobe not found — skipping duration check")
        return True

    try:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             str(pipeline_result.output_path)],
            capture_output=True, text=True, timeout=15
        )
        duration = float(r.stdout.strip())
        logger.info("Video duration: %.1f seconds (%.1f minutes)", duration, duration / 60)
        ok = check("Duration >= 30 seconds", duration >= 30, f"{duration:.1f}s")
        ok &= check("Duration <= 10 minutes", duration <= 600, f"{duration:.1f}s")
        return ok
    except Exception as exc:
        logger.error("Duration check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("RAGAI End-to-End Test — target: %d-minute video", int(TARGET_MINS))
    logger.info("Topic: %s", TEST_TOPIC)
    logger.info("Output dir: %s", TEST_DIR.resolve())

    results = {}
    t_total = time.time()

    # Stages that don't need pipeline result
    app_config, ok = test_config();           results["config"] = ok
    if not ok:
        logger.error("Config failed — aborting")
        sys.exit(1)

    score_result, ok = test_topic_quality();  results["topic_quality"] = ok
    ok = test_engagement(score_result["score"]); results["engagement"] = ok
    _, ok = test_narrative();                 results["narrative"] = ok
    _, ok = test_content_variation();         results["content_variation"] = ok
    archive, ok = test_story_archive();       results["story_archive"] = ok

    # Full pipeline
    pipeline_result, ok = test_pipeline(app_config); results["pipeline"] = ok

    # Post-pipeline stages
    ok = test_thumbnails(pipeline_result);    results["thumbnails"] = ok
    ok = test_archive_save(archive, pipeline_result); results["archive_save"] = ok
    ok = test_video_duration(pipeline_result); results["video_duration"] = ok

    # Summary
    section("TEST SUMMARY")
    total_elapsed = time.time() - t_total
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    for stage, ok in results.items():
        status = "PASS" if ok else "FAIL"
        logger.info("  [%s] %s", status, stage)

    logger.info("\nTotal: %d passed, %d failed — %.1fs", passed, failed, total_elapsed)

    # Write JSON report
    report = {
        "topic": TEST_TOPIC,
        "scene_count": SCENE_COUNT,
        "target_minutes": TARGET_MINS,
        "results": {k: ("PASS" if v else "FAIL") for k, v in results.items()},
        "passed": passed,
        "failed": failed,
        "elapsed_seconds": round(total_elapsed, 1),
        "output_dir": str(TEST_DIR.resolve()),
    }
    report_path = TEST_DIR / "test_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Report saved: %s", report_path)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
