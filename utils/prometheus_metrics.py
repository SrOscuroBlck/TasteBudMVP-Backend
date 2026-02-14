from typing import Optional
try:
    from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

from utils.logger import setup_logger

logger = setup_logger(__name__)


class PrometheusMetrics:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled and PROMETHEUS_AVAILABLE
        
        if not PROMETHEUS_AVAILABLE and enabled:
            logger.warning(
                "Prometheus metrics requested but prometheus_client not installed. "
                "Install with: pip install prometheus_client"
            )
        
        if self.enabled:
            self.registry = CollectorRegistry()
            
            self.request_count = Counter(
                'tastebud_requests_total',
                'Total number of requests',
                ['method', 'endpoint', 'status'],
                registry=self.registry
            )
            
            self.request_duration = Histogram(
                'tastebud_request_duration_seconds',
                'Request duration in seconds',
                ['method', 'endpoint'],
                registry=self.registry
            )
            
            self.recommendation_count = Counter(
                'tastebud_recommendations_total',
                'Total number of recommendations generated',
                ['user_id'],
                registry=self.registry
            )
            
            self.recommendation_duration = Histogram(
                'tastebud_recommendation_duration_seconds',
                'Recommendation generation duration in seconds',
                registry=self.registry
            )
            
            self.faiss_search_duration = Histogram(
                'tastebud_faiss_search_duration_seconds',
                'FAISS search duration in seconds',
                registry=self.registry
            )
            
            self.index_size = Gauge(
                'tastebud_faiss_index_size',
                'Number of items in FAISS index',
                ['dimension'],
                registry=self.registry
            )
            
            self.feedback_count = Counter(
                'tastebud_feedback_total',
                'Total feedback events',
                ['feedback_type'],
                registry=self.registry
            )
            
            logger.info("Prometheus metrics initialized successfully")
    
    def record_request(self, method: str, endpoint: str, status: int, duration_seconds: float):
        if not self.enabled:
            return
        
        self.request_count.labels(method=method, endpoint=endpoint, status=status).inc()
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration_seconds)
    
    def record_recommendation(self, user_id: str, duration_seconds: float):
        if not self.enabled:
            return
        
        self.recommendation_count.labels(user_id=user_id).inc()
        self.recommendation_duration.observe(duration_seconds)
    
    def record_faiss_search(self, duration_seconds: float):
        if not self.enabled:
            return
        
        self.faiss_search_duration.observe(duration_seconds)
    
    def set_index_size(self, dimension: int, size: int):
        if not self.enabled:
            return
        
        self.index_size.labels(dimension=str(dimension)).set(size)
    
    def record_feedback(self, feedback_type: str):
        if not self.enabled:
            return
        
        self.feedback_count.labels(feedback_type=feedback_type).inc()
    
    def generate_metrics(self) -> bytes:
        if not self.enabled:
            return b""
        
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        if not self.enabled:
            return "text/plain"
        
        return CONTENT_TYPE_LATEST


prometheus_metrics: Optional[PrometheusMetrics] = None


def init_prometheus_metrics(enabled: bool = False) -> PrometheusMetrics:
    global prometheus_metrics
    prometheus_metrics = PrometheusMetrics(enabled=enabled)
    return prometheus_metrics


def get_prometheus_metrics() -> Optional[PrometheusMetrics]:
    return prometheus_metrics
