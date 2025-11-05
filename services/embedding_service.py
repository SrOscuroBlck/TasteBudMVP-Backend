from typing import List, Optional, Dict, Any
from datetime import datetime
from openai import OpenAI
import numpy as np

from config.settings import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class EmbeddingService:
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = "text-embedding-3-small"
        self.embedding_dim = 1536
        self._sentence_model = None
    
    def _get_sentence_model(self):
        if self._sentence_model is None:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._sentence_model
    
    def _normalize_embedding_dimension(self, embedding: np.ndarray) -> List[float]:
        if embedding.size < self.embedding_dim:
            pad_width = self.embedding_dim - embedding.size
            embedding = np.pad(embedding, (0, pad_width))
        else:
            embedding = embedding[:self.embedding_dim]
        return embedding.tolist()
    
    def generate_text_for_item(self, item: Dict[str, Any]) -> str:
        parts = []
        
        if name := item.get("name"):
            parts.append(f"Dish: {name}")
        
        if description := item.get("description"):
            parts.append(f"Description: {description}")
        
        if ingredients := item.get("ingredients"):
            if isinstance(ingredients, list):
                parts.append(f"Ingredients: {', '.join(ingredients)}")
        
        if cuisine := item.get("cuisine"):
            if isinstance(cuisine, list):
                parts.append(f"Cuisine: {', '.join(cuisine)}")
        
        if cooking_method := item.get("cooking_method"):
            parts.append(f"Cooking method: {cooking_method}")
        
        if dietary_tags := item.get("dietary_tags"):
            if isinstance(dietary_tags, list) and dietary_tags:
                parts.append(f"Dietary: {', '.join(dietary_tags)}")
        
        if course := item.get("course"):
            parts.append(f"Course: {course}")
        
        if spice_level := item.get("spice_level"):
            parts.append(f"Spice level: {spice_level}/5")
        
        return ". ".join(parts)
    
    def generate_embedding_openai(self, text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI API"""
        if not self.client:
            return None
        
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("OpenAI embedding failed, will use fallback", extra={"error": str(e), "model": self.model})
            return None
    
    def generate_embedding_local(self, text: str) -> List[float]:
        """Generate embedding using local sentence-transformers model"""
        model = self._get_sentence_model()
        embedding = model.encode(text, convert_to_numpy=True)
        embedding = np.asarray(embedding, dtype=np.float32)
        return self._normalize_embedding_dimension(embedding)
    
    def generate_embedding(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate embedding for a menu item.
        Returns dict with embedding, model info, and metadata.
        """
        text = self.generate_text_for_item(item)
        
        # Try OpenAI first
        embedding = self.generate_embedding_openai(text)
        model_used = self.model
        
        # Fallback to local
        if embedding is None:
            embedding = self.generate_embedding_local(text)
            model_used = "sentence-transformers/all-MiniLM-L6-v2"
        
        if embedding is None:
            return None
        
        return {
            "embedding": embedding,
            "embedding_model": model_used,
            "embedding_version": "1.0",
            "last_embedded_at": datetime.utcnow(),
            "source_text": text
        }
    
    def generate_batch_openai(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Generate embeddings for multiple texts in one OpenAI API call"""
        if not self.client:
            return None
        
        try:
            response = self.client.embeddings.create(
                input=texts,
                model=self.model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.warning("OpenAI batch embedding failed, will use fallback", extra={"error": str(e), "batch_size": len(texts), "model": self.model})
            return None
    
    def generate_batch_local(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts using local model"""
        model = self._get_sentence_model()
        embeddings = model.encode(texts, convert_to_numpy=True)
        embeddings = np.asarray(embeddings, dtype=np.float32)
        
        return [self._normalize_embedding_dimension(embedding) for embedding in embeddings]
    
    def generate_batch(self, items: List[Dict[str, Any]], batch_size: int = 100) -> List[Optional[Dict[str, Any]]]:
        """
        Generate embeddings for multiple items in batches.
        Uses true batch processing - one API call per batch instead of N individual calls.
        More efficient for large datasets.
        """
        results = []
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            texts = [self.generate_text_for_item(item) for item in batch]
            
            # Try OpenAI batch API first
            embeddings = self.generate_batch_openai(texts)
            model_used = self.model
            
            # Fallback to local batch processing
            if embeddings is None:
                embeddings = self.generate_batch_local(texts)
                model_used = "sentence-transformers/all-MiniLM-L6-v2"
            
            # Convert embeddings to result dictionaries
            timestamp = datetime.utcnow()
            for embedding, text in zip(embeddings, texts):
                results.append({
                    "embedding": embedding,
                    "embedding_model": model_used,
                    "embedding_version": "1.0",
                    "last_embedded_at": timestamp,
                    "source_text": text
                })
        
        return results
