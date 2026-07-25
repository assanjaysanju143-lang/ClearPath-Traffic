"""
ClearPath Vehicle Detector — CLI
Built on Ultralytics YOLO26 by default (swap with --family yolo11 / yolov8).

Usage examples:

  # Detect in an image
  python run.py --image road.jpg

  # Process a video file
  python run.py --video traffic.mp4

  # Use webcam (camera 0)
  python run.py --webcam

  # RTSP stream (CCTV camera)
  python run.py --rtsp rtsp://192.168.1.10:554/stream

  # Start ML API server
  python run.py --server

  # Use larger model for better accuracy
  python run.py --video traffic.mp4 --model s

  # Fall back to an older model generation
  python run.py --video traffic.mp4 --family yolo11

  # Save annotated output video
  python run.py --video traffic.mp4 --output result.mp4
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="ClearPath Vehicle Detector (YOLO26 by default)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image",  type=str, help="Path to image file")
    group.add_argument("--video",  type=str, help="Path to video file")
    group.add_argument("--webcam", action="store_true", help="Use webcam (camera 0)")
    group.add_argument("--rtsp",   type=str, help="RTSP stream URL")
    group.add_argument("--server", action="store_true", help="Start ML API server on port 8001")

    parser.add_argument("--model",      default="n", choices=["n","s","m","l"], help="Model size (nano/small/medium/large)")
    parser.add_argument("--family",     default="yolo26", choices=["yolo26","yolo11","yolov8"], help="YOLO generation to use")
    parser.add_argument("--conf",       default=0.35, type=float, help="Detection confidence (0–1)")
    parser.add_argument("--output",     default=None, help="Output video path")
    parser.add_argument("--skip",       default=2, type=int, help="Process every Nth frame")
    parser.add_argument("--no-window",  action="store_true", help="Don't show live window")
    args = parser.parse_args()

    if args.server:
        print("[Server] Starting ML API on http://localhost:8001")
        print("[Server] Docs: http://localhost:8001/docs")
        import uvicorn
        uvicorn.run("ml_api:app", host="0.0.0.0", port=8001, reload=False)
        return

    from processor import TrafficVideoProcessor
    proc = TrafficVideoProcessor(model_size=args.model, confidence=args.conf, model_family=args.family)

    if args.image:
        if not Path(args.image).exists():
            print(f"[Error] File not found: {args.image}")
            return
        result = proc.process_image(args.image)
        print(f"\n✓ Done! Check {Path(args.image).stem}_detected.jpg")

    elif args.video:
        if not Path(args.video).exists():
            print(f"[Error] File not found: {args.video}")
            return
        proc.process_video(
            source=args.video,
            output_path=args.output,
            show_window=not args.no_window,
            skip_frames=args.skip,
        )

    elif args.webcam:
        print("[Webcam] Opening camera 0 — press Q to quit")
        proc.process_video(
            source=0,
            output_path=args.output,
            show_window=True,
            skip_frames=args.skip,
        )

    elif args.rtsp:
        print(f"[RTSP] Connecting to {args.rtsp}")
        proc.process_video(
            source=args.rtsp,
            output_path=args.output,
            show_window=not args.no_window,
            skip_frames=args.skip,
        )


if __name__ == "__main__":
    main()
