from __future__ import annotations
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlmodel import Session
from models.restaurant import Restaurant, MenuItem
from models.ingestion import MenuUpload, IngestionStatus, IngestionSource, MenuParsingResult, ParsedMenuItem
from services.features import build_item_features, canonicalize_ingredient
from .pdf_processor import PDFProcessor, PDFExtractionError
from .menu_parser import MenuParser, MenuParsingError


class IngestionOrchestrator:
    def __init__(self):
        self.pdf_processor = PDFProcessor()
        self.menu_parser = MenuParser()
    
    def process_pdf_upload(
        self,
        session: Session,
        restaurant_id: UUID,
        file_path: str,
        original_filename: Optional[str] = None
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
            
            parsing_result = self._parse_menu(extracted_text, restaurant.name)
            upload.parsed_data = parsing_result.dict() if hasattr(parsing_result, 'dict') else parsing_result.model_dump()
            session.commit()
            
            menu_items = self._create_menu_items(session, restaurant_id, parsing_result)
            
            upload.items_created = len(menu_items)
            upload.status = IngestionStatus.COMPLETED
            
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
    
    def _parse_menu(self, extracted_text: str, restaurant_name: Optional[str] = None) -> MenuParsingResult:
        parsing_result = self.menu_parser.parse_menu_text(extracted_text, restaurant_name)
        
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
        
        return created_items
    
    def _build_menu_item(self, restaurant_id: UUID, parsed_item: ParsedMenuItem) -> MenuItem:
        normalized_ingredients = [
            canonicalize_ingredient(ing) for ing in parsed_item.ingredients
        ]
        
        normalized_tags = [tag.lower() for tag in parsed_item.dietary_tags]
        
        features = build_item_features(
            normalized_ingredients, 
            normalized_tags,
            item_name=parsed_item.name,
            item_description=parsed_item.description
        )
        
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
            features=features,
            provenance={
                "source": "pdf_upload",
                "ingestion_method": "llm_extraction",
                "raw_text": parsed_item.raw_text
            },
            inference_confidence=parsed_item.inference_confidence
        )
