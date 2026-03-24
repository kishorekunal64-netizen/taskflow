"""
topic_engine.py — Automatic clip grouping by topic/hashtag for RAGAI Editor V2.

Groups clips whose hashtags share related keywords into named compilation groups.
A group is created when 3 or more clips share related tags.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from clip_manager import Clip

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tag synonym clusters — tags in the same cluster are treated as related
# ---------------------------------------------------------------------------

_TAG_CLUSTERS: List[Tuple[str, List[str]]] = [
    ("Village",      ["village", "villagelife", "villagestory", "gaon", "gramin", "rural"]),
    ("Motivational", ["motivational", "motivation", "inspire", "inspirational", "success", "life"]),
    ("Devotional",   ["devotional", "bhakti", "spiritual", "god", "mandir", "pooja", "prayer"]),
    ("Love",         ["love", "romantic", "romance", "pyar", "ishq", "dil"]),
    ("Adventure",    ["adventure", "action", "thrill", "journey", "travel"]),
    ("Mystery",      ["mystery", "thriller", "suspense", "horror", "dark"]),
    ("Nature",       ["nature", "forest", "river", "mountain", "peaceful", "calm"]),
    ("Family",       ["family", "mother", "father", "children", "kids", "ghar", "home"]),
    ("History",      ["history", "historical", "ancient", "mythology", "legend", "epic"]),
    ("Comedy",       ["comedy", "funny", "humor", "hasya", "entertainment"]),
]

# Build reverse lookup: normalised_tag → cluster_name
_TAG_TO_CLUSTER: Dict[str, str] = {}
for _cluster_name, _keywords in _TAG_CLUSTERS:
    for _kw in _keywords:
        _TAG_TO_CLUSTER[_kw.lower()] = _cluster_name


@dataclass
class CompilationGroup:
    """A set of clips that share a common topic cluster."""
    group_id: str
    cluster_name: str
    title: str                          # human-readable compilation title
    clips: List[Clip] = field(default_factory=list)

    @property
    def clip_count(self) -> int:
        return len(self.clips)

    @property
    def total_duration(self) -> float:
        return sum(c.duration for c in self.clips)

    @property
    def total_duration_str(self) -> str:
        s = int(self.total_duration)
        return f"{s // 60}m {s % 60:02d}s"


def _normalise_tag(tag: str) -> str:
    """Strip # and lowercase."""
    return re.sub(r"[^a-z0-9]", "", tag.lower().lstrip("#"))


def _cluster_for_tag(tag: str) -> Optional[str]:
    norm = _normalise_tag(tag)
    return _TAG_TO_CLUSTER.get(norm)


def _clusters_for_clip(clip: Clip) -> List[str]:
    """Return all cluster names matched by this clip's tags (deduplicated)."""
    seen = set()
    result = []
    for tag in clip.tags:
        c = _cluster_for_tag(tag)
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    # Also try topic words
    for word in re.split(r"\W+", clip.topic or ""):
        c = _cluster_for_tag(word)
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _compilation_title(cluster_name: str) -> str:
    titles = {
        "Village":      "Village Stories Compilation",
        "Motivational": "Motivational Stories Compilation",
        "Devotional":   "Devotional Stories Compilation",
        "Love":         "Love Stories Compilation",
        "Adventure":    "Adventure Stories Compilation",
        "Mystery":      "Mystery & Thriller Compilation",
        "Nature":       "Nature & Peaceful Stories Compilation",
        "Family":       "Family Stories Compilation",
        "History":      "Historical & Mythological Compilation",
        "Comedy":       "Comedy & Entertainment Compilation",
    }
    return titles.get(cluster_name, f"{cluster_name} Stories Compilation")


class TopicEngine:
    """Groups clips into compilation groups based on shared tag clusters."""

    MIN_CLIPS = 3   # minimum clips to form a group

    def group_clips(self, clips: List[Clip]) -> List[CompilationGroup]:
        """
        Analyse all clips and return groups with >= MIN_CLIPS members.
        A clip can appear in multiple groups if it matches multiple clusters.
        """
        bucket: Dict[str, List[Clip]] = defaultdict(list)

        for clip in clips:
            for cluster in _clusters_for_clip(clip):
                bucket[cluster].append(clip)

        groups: List[CompilationGroup] = []
        for cluster_name, matched_clips in bucket.items():
            if len(matched_clips) >= self.MIN_CLIPS:
                group = CompilationGroup(
                    group_id=f"group_{cluster_name.lower()}",
                    cluster_name=cluster_name,
                    title=_compilation_title(cluster_name),
                    clips=matched_clips,
                )
                groups.append(group)
                logger.info(
                    "Group '%s': %d clips (%.0fs total)",
                    group.title, group.clip_count, group.total_duration,
                )

        if not groups:
            logger.info("No groups formed (need %d+ clips with shared tags)", self.MIN_CLIPS)

        return groups

    def best_group(self, clips: List[Clip]) -> Optional[CompilationGroup]:
        """Return the largest group, or None if none qualify."""
        groups = self.group_clips(clips)
        if not groups:
            return None
        return max(groups, key=lambda g: g.clip_count)
