from __future__ import annotations
from typing import Optional, List, Dict, Tuple
from uuid import UUID
from datetime import datetime
from sqlmodel import Session
from models.restaurant import Restaurant, MenuItem
from models.ingestion import MenuUpload, IngestionStatus, IngestionSource, MenuParsingResult, ParsedMenuItem
from services.features import build_item_features, canonicalize_ingredient
from services.llm_features import generate_llm_taste_profile
from services.embedding_service import EmbeddingService
from services.faiss_service import FAISSService
from services.similarity_matrix_service import SimilarityMatrixService
from .pdf_processor import PDFProcessor, PDFExtractionError
from .menu_parser import MenuParser, MenuParsingError


class IngestionOrchestrator:
    def __init__(self):
        self.pdf_processor = PDFProcessor()
        self.menu_parser = MenuParser()
        self.embedding_service = EmbeddingService()
    
    def process_pdf_upload(
        self,
        session: Session,
        restaurant_id: UUID,
        file_path: str,
        original_filename: Optional[str] = None,
        currency: Optional[str] = None
    ) -> MenuUpload:
        if not file_path:
            raise ValueError("file_path is required to process PDF upload")
        
        if not restaurant_id:
            raise ValueError("restaurant_id is required to process PDF upload")
        
        restaurant = session.get(Restaurant, restaurant_id)
        if not restaurant:
            raise ValueError(f"Restaurant {restaurant_id} not found")
        
        upload = MenuUpload(
            restaurant_id=restaurant_id,
            source_type=IngestionSource.PDF,
            status=IngestionStatus.PROCESSING,
            file_path=file_path,
            original_filename=original_filename
        )
        session.add(upload)
        session.commit()
        session.refresh(upload)
        
        start_time = datetime.utcnow()
        
        try:
            extracted_text = self._extract_text(file_path)
            upload.extracted_text = extracted_text
            session.commit()
            
            parsing_result = self._parse_menu(extracted_text, restaurant.name, currency)
            upload.parsed_data = parsing_result.dict() if hasattr(parsing_result, 'dict') else parsing_result.model_dump()
            session.commit()
            
            menu_items = self._create_menu_items(session, restaurant_id, parsing_result)
            
            upload.items_created = len(menu_items)
            upload.status = IngestionStatus.COMPLETED
            
            # Rebuild indexes in background after successful ingestion
            if len(menu_items) > 0:
                self._rebuild_indexes_async(session)
            
        except (PDFExtractionError, MenuParsingError, ValueError) as e:
            upload.status = IngestionStatus.FAILED
            upload.error_message = str(e)
        except Exception as e:
            upload.status = IngestionStatus.FAILED
            upload.error_message = f"Unexpected error: {str(e)}"
        
        end_time = datetime.utcnow()
        upload.processing_time_seconds = (end_time - start_time).total_seconds()
        upload.updated_at = end_time
        session.commit()
        session.refresh(upload)
        
        return upload
    
    def _extract_text(self, file_path: str) -> str:
        extracted_text = self.pdf_processor.extract_text_from_pdf(file_path)
        
        if not self.pdf_processor.validate_extracted_text(extracted_text):
            raise PDFExtractionError("Extracted text failed validation")
        
        return extracted_text
    
    def _parse_menu(self, extracted_text: str, restaurant_name: Optional[str] = None, currency: Optional[str] = None) -> MenuParsingResult:
        parsing_result = self.menu_parser.parse_menu_text(extracted_text, restaurant_name, currency)
        
        if not parsing_result.menu_items:
            raise MenuParsingError("No menu items were extracted")
        
        return parsing_result
    
    def _create_menu_items(
        self,
        session: Session,
        restaurant_id: UUID,
        parsing_result: MenuParsingResult
    ) -> List[MenuItem]:
        created_items = []
        
        for parsed_item in parsing_result.menu_items:
            menu_item = self._build_menu_item(restaurant_id, parsed_item)
            session.add(menu_item)
            created_items.append(menu_item)
        
        session.commit()
        
        for item in created_items:
            session.refresh(item)
            self._generate_embeddings_for_item(item)
        
        session.commit()
        
        return created_items
    
    def _generate_embeddings_for_item(self, item: MenuItem) -> None:
        try:
            text = f"{item.name}. {item.description or ''}. Ingredients: {', '.join(item.ingredients or [])}"
            
            embedding = self.embedding_service.generate_embedding_openai(text)
            if embedding:
                item.embedding = embedding
                item.embedding_model = "text-embedding-3-small"
                item.last_embedded_at = datetime.utcnow()
                
                reduced = self.embedding_service.reduce_embedding(embedding, target_dim=64)
                if reduced:
                    item.reduced_embedding = reduced
        except Exception as e:
            pass
    
    def _rebuild_indexes_async(self, session: Session) -> None:
        try:
            from sqlmodel import select
            
            # Rebuild FAISS 64D index
            items_with_reduced = session.exec(
                select(MenuItem).where(MenuItem.reduced_embedding.is_not(None))
            ).all()
            
            if items_with_reduced and len(items_with_reduced) > 0:
                embeddings = [item.reduced_embedding for item in items_with_reduced]
                item_ids = [item.id for item in items_with_reduced]
                
                faiss_service = FAISSService()
                faiss_service.build_index(embeddings, item_ids, dimension=64)
                faiss_service.save("current")
            
            # Rebuild similarity matrix
            items_with_features = session.exec(
                select(MenuItem).where(MenuItem.features.is_not(None))
            ).all()
            
            if items_with_features and len(items_with_features) > 0:
                similarity_service = SimilarityMatrixService()
                similarity_service.build_matrix(items_with_features)
                similarity_service.save_to_disk("data/faiss_indexes/similarity_matrix.pkl")
        
        except Exception as e:
            pass
    
    def _build_menu_item(self, restaurant_id: UUID, parsed_item: ParsedMenuItem) -> MenuItem:
        normalized_ingredients = [
            canonicalize_ingredient(ing) for ing in parsed_item.ingredients
        ]
        
        normalized_tags = [tag.lower() for tag in parsed_item.dietary_tags]
        
        taste, texture, richness = generate_full_item_profile(
            parsed_item.name,
            parsed_item.description,
            normalized_ingredients,
            normalized_tags
        )
        
        feature_generation_method = determine_profile_generation_method(taste, parsed_item)
        
        return MenuItem(
            restaurant_id=restaurant_id,
            name=parsed_item.name,
            description=parsed_item.description,
            ingredients=normalized_ingredients,
            allergens=[allergen.lower() for allergen in parsed_item.allergens],
            dietary_tags=normalized_tags,
            cuisine=[cuisine.lower() for cuisine in parsed_item.cuisine],
            price=parsed_item.price,
            spice_level=parsed_item.spice_level,
            cooking_method=parsed_item.cooking_method,
            course=parsed_item.course,
            features=taste,
            texture=texture,
            richness=richness,
            provenance={
                "source": "pdf_upload",
                "ingestion_method": "llm_extraction",
                "feature_generation_method": feature_generation_method,
                "llm_taste_profile": taste,
                "llm_texture_profile": texture,
                "llm_richness": richness,
                "raw_text": parsed_item.raw_text
            },
            inference_confidence=parsed_item.inference_confidence
        )


def generate_full_item_profile(
    item_name: str,
    item_description: str,
    normalized_ingredients: List[str],
    normalized_tags: List[str]
) -> Tuple[Dict[str, float], Dict[str, float], Optional[float]]:
    taste_llm, texture_llm, richness_llm, cuisine_typicality = generate_llm_taste_profile(
        item_name,
        item_description,
        normalized_ingredients
    )
    
    if taste_llm and len(taste_llm) > 0:
        return (taste_llm, texture_llm, richness_llm)
    
    taste_keywords = build_item_features(
        normalized_ingredients,
        normalized_tags,
        item_name,
        item_description
    )
    
    return (taste_keywords, {}, None)


def determine_profile_generation_method(taste_profile: Dict[str, float], parsed_item: ParsedMenuItem) -> str:
    if not taste_profile:
        return "none"
    
    has_name_or_description = parsed_item.name or parsed_item.description
    
    if has_name_or_description:
        return "llm"
    
    return "keyword"
