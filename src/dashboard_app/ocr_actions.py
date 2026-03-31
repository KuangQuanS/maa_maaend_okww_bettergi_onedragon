from __future__ import annotations

from pathlib import Path

import numpy as np

from .input_utils import click_screen
from .models import OCRActionSpec
from .window_utils import WindowInfo, find_windows

try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None  # type: ignore

try:
    import mss  # type: ignore
except ImportError:
    mss = None  # type: ignore

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except ImportError:
    RapidOCR = None  # type: ignore


class OCRActionExecutor:
    def __init__(self) -> None:
        self._ocr_engine = RapidOCR() if RapidOCR is not None else None

    def available(self) -> bool:
        return self._ocr_engine is not None and mss is not None and cv2 is not None

    def _target_window(self, action: OCRActionSpec) -> WindowInfo | None:
        matches = find_windows(title_contains=action.window_title, class_contains=action.window_class, visible_only=False)
        return matches[0] if matches else None

    def _capture(self, window: WindowInfo, action: OCRActionSpec) -> tuple[np.ndarray, dict[str, int]]:
        if mss is None:
            raise RuntimeError("mss is not installed")
        left, top, right, bottom = window.rect
        region = {
            "left": left + action.roi.x,
            "top": top + action.roi.y,
            "width": action.roi.width or max(right - left, 1),
            "height": action.roi.height or max(bottom - top, 1),
        }
        with mss.mss() as sct:
            raw = np.array(sct.grab(region))
        frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR) if cv2 is not None else raw
        return frame, region

    def execute(self, action: OCRActionSpec) -> tuple[bool, str]:
        if not action.enabled:
            return False, "OCR fallback is disabled."
        if not self.available():
            return False, "OCR dependencies are not available."
        window = self._target_window(action)
        if window is None:
            return False, "No matching BetterGI window was found for OCR fallback."
        for attempt in range(1, action.max_retry + 1):
            frame, region = self._capture(window, action)
            if action.action_type == "template_click":
                ok, message = self._template_click(frame, region, action, window)
            else:
                ok, message = self._ocr_click(frame, region, action, window)
            if ok:
                return True, f"{message} (attempt {attempt})"
        return False, "OCR/template action did not find a clickable target."

    def _template_click(self, frame: np.ndarray, region: dict[str, int], action: OCRActionSpec, window: WindowInfo) -> tuple[bool, str]:
        if cv2 is None:
            return False, "OpenCV is not available."
        template_path = Path(action.template_path)
        if not template_path.exists():
            return False, "Template file does not exist."
        template = cv2.imread(str(template_path))
        if template is None:
            return False, "Template image could not be loaded."
        match = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(match)
        if max_val < 0.88:
            return False, f"Template confidence too low: {max_val:.2f}"
        click_x = region["left"] + max_loc[0] + template.shape[1] // 2 + action.click_offset.x
        click_y = region["top"] + max_loc[1] + template.shape[0] // 2 + action.click_offset.y
        click_screen(click_x, click_y, hwnd=window.hwnd)
        return True, f"Clicked template target at {click_x},{click_y}"

    def _ocr_click(self, frame: np.ndarray, region: dict[str, int], action: OCRActionSpec, window: WindowInfo) -> tuple[bool, str]:
        if self._ocr_engine is None:
            return False, "RapidOCR is not available."
        result, _ = self._ocr_engine(frame)
        if not result:
            return False, "OCR did not detect any text."
        needle = action.match_target.strip().lower()
        for box, text, _score in result:
            if needle and needle not in str(text).lower():
                continue
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            click_x = region["left"] + (min(xs) + max(xs)) // 2 + action.click_offset.x
            click_y = region["top"] + (min(ys) + max(ys)) // 2 + action.click_offset.y
            click_screen(click_x, click_y, hwnd=window.hwnd)
            return True, f"Clicked OCR target '{text}' at {click_x},{click_y}"
        return False, f"OCR did not find text matching '{action.match_target}'."
