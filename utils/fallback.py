from typing import TypeVar, Callable, Optional, List
from functools import wraps

from utils.logger import setup_logger

logger = setup_logger(__name__)

T = TypeVar('T')


def with_fallback(
    fallback_func: Callable[..., T],
    exception_types: tuple = (Exception,),
    log_errors: bool = True
) -> Callable:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                if log_errors:
                    logger.warning(
                        f"Function {func.__name__} failed, using fallback",
                        extra={
                            "function": func.__name__,
                            "error": str(e),
                            "fallback": fallback_func.__name__
                        }
                    )
                return fallback_func(*args, **kwargs)
        return wrapper
    return decorator


class FallbackChain:
    def __init__(self, chain_name: str):
        self.chain_name = chain_name
        self.functions: List[Callable] = []
    
    def add(self, func: Callable) -> 'FallbackChain':
        self.functions.append(func)
        return self
    
    def execute(self, *args, **kwargs) -> Optional[T]:
        if not self.functions:
            raise ValueError(f"fallback chain {self.chain_name} has no functions")
        
        last_error = None
        
        for i, func in enumerate(self.functions):
            try:
                logger.debug(
                    f"Executing function {i+1}/{len(self.functions)} in fallback chain",
                    extra={
                        "chain": self.chain_name,
                        "function": func.__name__,
                        "position": i + 1
                    }
                )
                
                result = func(*args, **kwargs)
                
                if i > 0:
                    logger.info(
                        f"Fallback succeeded at position {i+1}",
                        extra={
                            "chain": self.chain_name,
                            "function": func.__name__,
                            "position": i + 1
                        }
                    )
                
                return result
                
            except Exception as e:
                last_error = e
                
                logger.warning(
                    f"Function failed in fallback chain",
                    extra={
                        "chain": self.chain_name,
                        "function": func.__name__,
                        "position": i + 1,
                        "error": str(e)
                    }
                )
                
                if i == len(self.functions) - 1:
                    logger.error(
                        f"All functions in fallback chain failed",
                        extra={
                            "chain": self.chain_name,
                            "total_functions": len(self.functions)
                        }
                    )
        
        if last_error:
            raise last_error
        
        return None


def create_recommendation_fallback_chain():
    chain = FallbackChain("recommendation")
    
    def primary_recommendation(*args, **kwargs):
        from services.recommendation_service import RecommendationService
        service = RecommendationService()
        return service.recommend(*args, **kwargs)
    
    def faiss_only_recommendation(*args, **kwargs):
        from services.retrieval_service import RetrievalService
        from sqlmodel import Session
        
        session = kwargs.get('session')
        user = kwargs.get('user')
        
        if not session or not user:
            raise ValueError("session and user required for fallback")
        
        retrieval_service = RetrievalService()
        items = retrieval_service.retrieve_candidates(
            session=session,
            user=user,
            k=kwargs.get('n_recommendations', 10)
        )
        
        return {"items": items, "fallback": "faiss_only"}
    
    def random_popular_fallback(*args, **kwargs):
        from sqlmodel import Session, select
        from models.restaurant import MenuItem
        
        session = kwargs.get('session')
        
        if not session:
            raise ValueError("session required for fallback")
        
        items = session.exec(
            select(MenuItem)
            .order_by(MenuItem.popularity_score.desc())
            .limit(kwargs.get('n_recommendations', 10))
        ).all()
        
        return {"items": list(items), "fallback": "popular"}
    
    chain.add(primary_recommendation)
    chain.add(faiss_only_recommendation)
    chain.add(random_popular_fallback)
    
    return chain
