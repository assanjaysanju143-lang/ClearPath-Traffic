"""
Traffic Video Processor
Processes video files, webcam feeds, or RTSP streams.
Outputs annotated video + per-frame traffic ratio data.
"""

import cv2
import time
import json
from pathlib import Path
from collections import deque
from detector import VehicleDetector, DetectionResult


class TrafficVideoProcessor:
    def __init__(self, model_size: str = "n", confidence: float = 0.35, model_family: str = "yolo26"):
        self.detector = VehicleDetector(model_size, confidence, model_family)
        self.results_history = []
        # Smooth traffic ratio over last N frames
        self.ratio_buffer = deque(maxlen=15)

    def process_image(self, image_path: str, zone=None, save_output: bool = True) -> DetectionResult:
        """Process a single image file."""
        frame = cv2.imread(image_path)
        if frame is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")

        result = self.detector.detect_frame(frame, zone)

        if save_output:
            out_path = Path(image_path).stem + "_detected.jpg"
            cv2.imwrite(out_path, result.annotated_frame)
            print(f"[Output] Saved to {out_path}")

        self._print_result(result)
        return result

    def process_video(
        self,
        source,                   # file path, 0 for webcam, or RTSP URL
        zone=None,
        output_path: str = None,
        show_window: bool = True,
        skip_frames: int = 2,     # process every Nth frame (speeds up processing)
    ):
        """
        Process video/webcam/RTSP stream.
        source: 'video.mp4' | 0 (webcam) | 'rtsp://...'
        """
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video source: {source}")

        w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_in = cap.get(cv2.CAP_PROP_FPS) or 30

        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_path, fourcc, fps_in / max(skip_frames, 1), (w, h))
            print(f"[Output] Writing to {output_path}")

        print(f"[Video] Source: {source} | {w}x{h} @ {fps_in:.0f}fps")
        print("[Video] Press 'q' to quit, 's' to save snapshot, 'z' to define zone")

        frame_idx = 0
        t_prev = time.time()
        last_result = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1

            # Only run detection every Nth frame
            if frame_idx % skip_frames == 0:
                t_now = time.time()
                fps = 1.0 / max(t_now - t_prev, 0.001)
                t_prev = t_now

                result = self.detector.detect_frame(frame, zone)
                result.fps = round(fps, 1)
                last_result = result

                self.ratio_buffer.append(result.traffic_ratio)
                smoothed = sum(self.ratio_buffer) / len(self.ratio_buffer)
                result.traffic_ratio = round(smoothed, 3)

                self.results_history.append({
                    "frame": frame_idx,
                    "total": result.total_vehicles,
                    "density": result.weighted_density,
                    "level": result.density_level,
                    "ratio": result.traffic_ratio,
                    "fps": result.fps,
                })

                # Draw FPS on frame
                cv2.putText(
                    result.annotated_frame,
                    f"FPS: {fps:.1f}",
                    (w - 100, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA
                )

                display = result.annotated_frame
            else:
                display = frame if last_result is None else last_result.annotated_frame

            if writer:
                writer.write(display)

            if show_window:
                cv2.imshow("ClearPath — Vehicle Detector", display)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s') and last_result is not None:
                    snap = f"snapshot_frame{frame_idx}.jpg"
                    cv2.imwrite(snap, display)
                    print(f"[Snapshot] Saved {snap}")

        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()

        summary = self._summarize()
        self._save_report(summary)
        return summary

    def _print_result(self, r: DetectionResult):
        print(f"\n[Frame {r.frame_id}]")
        print(f"  Vehicles     : {r.total_vehicles}")
        print(f"  Counts       : {r.vehicle_counts}")
        print(f"  Weighted     : {r.weighted_density}")
        print(f"  Level        : {r.density_level}")
        print(f"  Traffic ratio: {r.traffic_ratio:.1%}")

    def _summarize(self) -> dict:
        if not self.results_history:
            return {}
        ratios = [r["ratio"] for r in self.results_history]
        levels = [r["level"] for r in self.results_history]
        return {
            "total_frames_analyzed": len(self.results_history),
            "avg_traffic_ratio": round(sum(ratios) / len(ratios), 3),
            "peak_traffic_ratio": round(max(ratios), 3),
            "min_traffic_ratio":  round(min(ratios), 3),
            "dominant_level": max(set(levels), key=levels.count),
            "frame_data": self.results_history[-50:],  # last 50 frames
        }

    def _save_report(self, summary: dict):
        with open("traffic_report.json", "w") as f:
            json.dump(summary, f, indent=2)
        print("\n[Report] Saved to traffic_report.json")
        print(f"[Summary] Avg ratio: {summary.get('avg_traffic_ratio', 0):.1%} | "
              f"Peak: {summary.get('peak_traffic_ratio', 0):.1%} | "
              f"Level: {summary.get('dominant_level', '—')}")
