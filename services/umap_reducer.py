from typing import List, Optional
import numpy as np
import umap


class UMAPReducer:
    """
    Dimensionality reduction service using UMAP.
    Reduces high-dimensional embeddings (1536) to lower dimensions (64) for faster FAISS search.
    """
    
    def __init__(self, n_components: int = 64, random_state: int = 42):
        self.n_components = n_components
        self.random_state = random_state
        self.reducer: Optional[umap.UMAP] = None
        self.is_fitted = False
    
    def fit(self, embeddings: List[List[float]]) -> None:
        """
        Fit UMAP reducer on a set of embeddings.
        Should be called once with a representative sample of your data.
        """
        if len(embeddings) < self.n_components:
            raise ValueError(f"Need at least {self.n_components} embeddings to fit UMAP")
        
        X = np.array(embeddings, dtype=np.float32)
        
        self.reducer = umap.UMAP(
            n_components=self.n_components,
            metric='cosine',
            random_state=self.random_state,
            n_neighbors=15,
            min_dist=0.1,
            verbose=True
        )
        
        self.reducer.fit(X)
        self.is_fitted = True
    
    def transform(self, embeddings: List[List[float]]) -> List[List[float]]:
        """
        Transform embeddings to reduced dimensionality.
        Requires fit() to be called first.
        """
        if not self.is_fitted:
            raise ValueError("UMAP reducer not fitted. Call fit() first.")
        
        X = np.array(embeddings, dtype=np.float32)
        reduced = self.reducer.transform(X)
        
        return reduced.tolist()
    
    def fit_transform(self, embeddings: List[List[float]]) -> List[List[float]]:
        """
        Fit and transform in one step.
        """
        self.fit(embeddings)
        return self.transform(embeddings)
    
    def save(self, path: str) -> None:
        """Save fitted UMAP model to disk"""
        if not self.is_fitted:
            raise ValueError("Cannot save unfitted reducer")
        
        import joblib
        joblib.dump(self.reducer, path)
    
    def load(self, path: str) -> None:
        """Load fitted UMAP model from disk"""
        import joblib
        self.reducer = joblib.load(path)
        if self.reducer.n_components != self.n_components:
            raise ValueError(f'Loaded reducer has {self.reducer.n_components} components, expected {self.n_components}')
        self.is_fitted = True
