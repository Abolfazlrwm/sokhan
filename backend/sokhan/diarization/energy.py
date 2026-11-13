"""Lightweight, dependency-free speaker-turn clustering.

This is a heuristic diarizer: it finds voiced regions by short-time energy
and splits them into at most two acoustic clusters using simple spectral
features. It is *not* a substitute for a neural speaker model (pyannote) —
its labels describe acoustic similarity, not verified identities. It exists
so self-hosters can get usable speaker marks on CPU without gated model
weights. See docs/adr/0004-diarization-engines.md.
"""

from __future__ import annotations

import logging

import numpy as np

from sokhan.diarization.base import SpeakerTurn

logger = logging.getLogger(__name__)

FRAME_SECONDS = 0.032
HOP_SECONDS = 0.010
WINDOW_SECONDS = 0.5
MIN_TURN_SECONDS = 0.8
GAP_FILL_SECONDS = 0.35
MERGE_GAP_SECONDS = 0.6
SPEECH_MARGIN_DB = 12.0
ABSOLUTE_FLOOR_DB = -45.0
MIN_LEVEL_SPREAD_DB = 6.0
CLUSTER_SPLIT_GAIN = 0.30  # k=2 must beat k=1 inertia by this fraction


def _frame_rms_db(samples: np.ndarray, frame: int, hop: int) -> np.ndarray:
    """RMS level in dBFS for every analysis frame."""
    count = 1 + (len(samples) - frame) // hop
    if count < 1:
        return np.zeros(0)
    windows = np.lib.stride_tricks.as_strided(
        samples,
        shape=(count, frame),
        strides=(samples.strides[0] * hop, samples.strides[0]),
    ).astype(np.float64)
    rms = np.sqrt(np.mean(windows**2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-9))


def _fill_short_gaps(mask: np.ndarray, max_gap_frames: int) -> np.ndarray:
    """Bridge silence gaps that have speech on both sides within reach."""
    filled = mask.copy()
    for index in range(len(mask)):
        if mask[index]:
            continue
        left = mask[max(0, index - max_gap_frames) : index + 1].any()
        right = mask[index : min(len(mask), index + max_gap_frames + 1)].any()
        filled[index] = left and right
    return filled


def _speech_mask(levels: np.ndarray) -> np.ndarray:
    """Decide which analysis frames are voiced.

    Digital silence yields no turns at all. When the dynamic range is too
    small to separate noise from speech (continuous speech, tones), every
    frame counts as voiced rather than discarding the whole file.
    """
    floor_level = float(np.percentile(levels, 20))
    ceiling_level = float(np.percentile(levels, 90))
    if ceiling_level < ABSOLUTE_FLOOR_DB:
        return np.zeros(levels.size, dtype=bool)
    if ceiling_level - floor_level < MIN_LEVEL_SPREAD_DB:
        return np.ones(levels.size, dtype=bool)
    threshold = max(
        min(floor_level + SPEECH_MARGIN_DB, (floor_level + ceiling_level) / 2.0),
        ABSOLUTE_FLOOR_DB,
    )
    mask = levels > threshold
    if not mask.any():
        mask = np.ones(levels.size, dtype=bool)
    return mask


def _windows_from_spans(
    spans: list[tuple[int, int]], sample_rate: int, min_window_samples: int
) -> list[tuple[int, int]]:
    """Fixed-size analysis windows inside every voiced span."""
    window = int(WINDOW_SECONDS * sample_rate)
    windows: list[tuple[int, int]] = []
    for start, end in spans:
        position = start
        while end - position >= window:
            windows.append((position, position + window))
            position += window
        if end - position >= min_window_samples:
            windows.append((position, end))
    return windows


def _spectral_features(
    samples: np.ndarray, sample_rate: int, spans: list[tuple[int, int]]
) -> np.ndarray:
    """Six log-band magnitudes plus zero-crossing rate per voiced span."""
    fft_size = 512
    band_edges = np.geomspace(100.0, min(4000.0, sample_rate / 2 - 100), 7)
    features = np.zeros((len(spans), 7), dtype=np.float64)
    for index, (start, end) in enumerate(spans):
        chunk = samples[start:end].astype(np.float64)
        window = chunk * np.hanning(len(chunk))
        spectrum = np.abs(np.fft.rfft(window, n=fft_size))
        freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)
        for band in range(6):
            in_band = (freqs >= band_edges[band]) & (freqs < band_edges[band + 1])
            features[index, band] = np.log10(max(float(spectrum[in_band].mean()), 1e-9))
        zcr = float(np.mean(np.abs(np.diff(np.sign(chunk)))) / 2.0) if len(chunk) > 1 else 0.0
        features[index, 6] = zcr
    mean = features.mean(axis=0, keepdims=True)
    std = features.std(axis=0, keepdims=True)
    return (features - mean) / np.maximum(std, 1e-9)


def _kmeans(points: np.ndarray, clusters: int, iterations: int = 25) -> tuple[np.ndarray, float]:
    """Tiny deterministic k-means; returns (labels, inertia)."""
    generator = np.random.default_rng(0)
    centroids = points[generator.choice(len(points), size=clusters, replace=False)].copy()
    labels = np.zeros(len(points), dtype=int)
    for _ in range(iterations):
        distances = ((points[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = distances.argmin(axis=1)
        for cluster in range(clusters):
            members = points[new_labels == cluster]
            if len(members):
                centroids[cluster] = members.mean(axis=0)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
    inertia = float(((points - centroids[labels]) ** 2).sum())
    return labels, inertia


class EnergyClusterDiarizer:
    """Two-cluster energy/VAD diarizer built on plain numpy."""

    name = "energy"

    def diarize(self, samples: np.ndarray, sample_rate: int) -> list[SpeakerTurn]:
        mono = samples.astype(np.float64)
        frame = int(FRAME_SECONDS * sample_rate)
        hop = int(HOP_SECONDS * sample_rate)
        if len(mono) < frame:
            return []

        levels = _frame_rms_db(mono, frame, hop)
        if levels.size == 0:
            return []
        mask = _speech_mask(levels)
        if not mask.any():
            return []
        mask = _fill_short_gaps(mask, max_gap_frames=int(GAP_FILL_SECONDS / HOP_SECONDS))

        # contiguous voiced sample ranges, dropping too-short fragments
        min_samples = int(MIN_TURN_SECONDS * sample_rate)
        spans: list[tuple[int, int]] = []
        start: int | None = None
        for index, active in enumerate(mask):
            if active and start is None:
                start = index
            elif not active and start is not None:
                spans.append((start * hop, index * hop))
                start = None
        if start is not None:
            spans.append((start * hop, len(mask) * hop))
        spans = [(a, b) for a, b in spans if b - a >= min_samples]
        if not spans:
            return []

        windows = _windows_from_spans(spans, sample_rate, frame)
        features = _spectral_features(mono, sample_rate, windows)
        labels = np.zeros(len(features), dtype=int)
        speakers = 1
        if len(features) >= 4:
            _, inertia_one = _kmeans(features, 1)
            labels_two, inertia_two = _kmeans(features, 2)
            # a split only counts when both clusters are substantial: a lone
            # outlier point escaping the pack is not a second speaker
            smallest = min(int((labels_two == 0).sum()), int((labels_two == 1).sum()))
            balanced = smallest >= max(2, round(0.25 * len(features)))
            if (
                inertia_one > 0
                and (inertia_one - inertia_two) / inertia_one >= CLUSTER_SPLIT_GAIN
                and balanced
            ):
                labels = labels_two
                speakers = 2

        # deterministic identity: the cluster with the stronger low-frequency
        # band (a crude pitch proxy) becomes SPK_1
        if speakers == 2:
            low_band = features[:, 0]
            means = [float(low_band[labels == c].mean()) for c in (0, 1)]
            first = 0 if means[0] >= means[1] else 1
            labels = np.where(labels == first, 0, 1)

        names = ["SPK_1", "SPK_2"]
        turns: list[SpeakerTurn] = []
        for (start, end), label in zip(windows, labels, strict=True):
            speaker = names[int(label)] if speakers == 2 else names[0]
            if (
                turns
                and turns[-1].speaker == speaker
                and start / sample_rate - turns[-1].end < MERGE_GAP_SECONDS
            ):
                turns[-1] = SpeakerTurn(turns[-1].start, float(end / sample_rate), speaker)
            else:
                turns.append(
                    SpeakerTurn(float(start / sample_rate), float(end / sample_rate), speaker)
                )
        return turns
