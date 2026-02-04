"""
Basic metrics middleware for operational monitoring.
Collects simple request metrics without external dependencies.
"""
import time
from typing import Dict, List
from collections import defaultdict, deque
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import get_settings


class BasicMetricsMiddleware(BaseHTTPMiddleware):
    """
    Basic metrics collection middleware.

    Tracks:
    - Request counts by endpoint and status
    - Response time percentiles
    - Error rates
    """

    def __init__(self, app, max_history: int = 1000):
        super().__init__(app)
        self.settings = get_settings()
        self.max_history = max_history

        # In-memory metrics storage
        self.request_counts: Dict[str, defaultdict] = defaultdict(lambda: defaultdict(int))
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self.error_rates: Dict[str, List[bool]] = defaultdict(lambda: deque(maxlen=max_history))

        # Store reference in app state for metrics endpoint
        if hasattr(app, 'state'):
            app.state._metrics_middleware = self

    async def dispatch(self, request: Request, call_next):
        if not self.settings.ENABLE_METRICS:
            # Skip metrics collection if disabled
            return await call_next(request)

        start_time = time.time()
        endpoint = self._get_endpoint_key(request)

        try:
            response = await call_next(request)
            status_code = response.status_code
            is_error = status_code >= 400

            # Record metrics
            self._record_request(endpoint, status_code, is_error, start_time)

            return response

        except Exception as e:
            # Record exception as error
            self._record_request(endpoint, 500, True, start_time)
            raise

    def _get_endpoint_key(self, request: Request) -> str:
        """Extract endpoint key for metrics."""
        path = request.url.path
        method = request.method

        # Simple path normalization (could be enhanced with path templates)
        if path.startswith("/api/v1/") and path.count("/") > 3:
            # Normalize resource endpoints
            parts = path.split("/")
            if len(parts) >= 4:
                return f"{method} /api/v1/{parts[3]}"

        return f"{method} {path}"

    def _record_request(self, endpoint: str, status_code: int, is_error: bool, start_time: float):
        """Record request metrics."""
        response_time = (time.time() - start_time) * 1000  # Convert to ms

        # Count requests by status
        self.request_counts[endpoint][f"status_{status_code}"] += 1
        self.request_counts[endpoint]["total"] += 1

        if is_error:
            self.request_counts[endpoint]["errors"] += 1

        # Store response time for percentile calculation
        self.response_times[endpoint].append(response_time)

        # Store error for rate calculation
        self.error_rates[endpoint].append(is_error)

    def get_metrics(self) -> Dict:
        """Get current metrics summary."""
        metrics = {
            "endpoints": {},
            "summary": {
                "total_requests": 0,
                "total_errors": 0,
                "overall_error_rate": 0.0
            }
        }

        total_requests = 0
        total_errors = 0

        for endpoint, counts in self.request_counts.items():
            endpoint_requests = counts.get("total", 0)
            endpoint_errors = counts.get("errors", 0)

            total_requests += endpoint_requests
            total_errors += endpoint_errors

            # Calculate percentiles for response times
            response_times_list = list(self.response_times[endpoint])
            response_times_list.sort()

            percentiles = {}
            if response_times_list:
                for p in [50, 95, 99]:
                    idx = int(len(response_times_list) * p / 100)
                    percentiles[f"p{p}"] = round(response_times_list[min(idx, len(response_times_list) - 1)], 2)

            # Calculate error rate
            error_rate = endpoint_errors / endpoint_requests if endpoint_requests > 0 else 0

            metrics["endpoints"][endpoint] = {
                "request_counts": dict(counts),
                "response_time_percentiles_ms": percentiles,
                "error_rate": round(error_rate, 4),
                "sample_size": len(response_times_list)
            }

        # Overall summary
        metrics["summary"]["total_requests"] = total_requests
        metrics["summary"]["total_errors"] = total_errors
        metrics["summary"]["overall_error_rate"] = round(
            total_errors / total_requests if total_requests > 0 else 0, 4
        )

        return metrics

    def reset_metrics(self):
        """Reset all metrics."""
        self.request_counts.clear()
        self.response_times.clear()
        self.error_rates.clear()
