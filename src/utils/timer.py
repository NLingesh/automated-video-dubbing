import time
from contextlib import contextmanager
from typing import Dict, Generator, List, Tuple


class StepTimer:
    """
    Measures the execution time of individual steps in a pipeline.
    Provides detailed statistics and formatting for reporting.
    """

    def __init__(self) -> None:
        self.steps: List[Tuple[str, float]] = []
        self.start_times: Dict[str, float] = {}

    def start(self, step_name: str) -> None:
        """
        Starts timing a specific step.
        """
        self.start_times[step_name] = time.perf_counter()

    def stop(self, step_name: str) -> float:
        """
        Stops timing a specific step, records the duration, and returns it.
        """
        if step_name not in self.start_times:
            raise ValueError(f"Step '{step_name}' was never started.")
        
        duration = time.perf_counter() - self.start_times[step_name]
        self.steps.append((step_name, duration))
        del self.start_times[step_name]
        return duration

    @contextmanager
    def time_step(self, step_name: str) -> Generator[None, None, None]:
        """
        A context manager for timing steps using a 'with' block.
        """
        self.start(step_name)
        try:
            yield
        finally:
            self.stop(step_name)

    def get_summary(self) -> Dict[str, float]:
        """
        Returns a dictionary of all recorded step names and their durations.
        """
        return {name: duration for name, duration in self.steps}

    def get_total_time(self) -> float:
        """
        Returns the sum of all recorded step durations.
        """
        return sum(duration for _, duration in self.steps)

    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Formats a duration in seconds into a human-readable string.
        """
        if seconds < 60:
            return f"{seconds:.2f}s"
        
        minutes, secs = divmod(seconds, 60)
        hours, mins = divmod(minutes, 60)
        
        if hours > 0:
            return f"{int(hours)}h {int(mins)}m {secs:.1f}s"
        return f"{int(mins)}m {secs:.1f}s"
