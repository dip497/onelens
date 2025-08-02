"""RFP Document API endpoints."""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
import pandas as pd
import io
import json
from datetime import datetime

from app.core.database import get_db
from app.models.rfp import RFPDocument, RFPQAPair
from app.models.enums import ProcessedStatus
from app.schemas.rfp import (
    RFPDocumentCreate,
    RFPDocumentUpdate,
    RFPDocumentResponse,
    RFPDocumentListResponse,
    RFPDocumentListItem,
    RFPQAPairCreate,
    RFPQAPairResponse,
    RFPProcessingRequest,
    RFPProcessingResponse,
    RFPAnalysisRequest,
    RFPAnalysisResponse,
)
from app.services.embedding import EmbeddingService
from app.services.rfp_processor import RFPProcessor
from app.tools import search_knowledge_base

router = APIRouter()
embedding_service = EmbeddingService()


async def extract_qa_with_llm(df):
    """
    Use Agno AI agent with structured output to intelligently extract Q&A pairs from any Excel structure.
    """
    try:
        # Import Agno components
        from agno.agent import Agent
        from agno.models.openai import OpenAIChat
        from pydantic import BaseModel, Field
        from typing import List
        import os

        # Check if OpenAI API key is available
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            print("OpenAI API key not found, using fallback extraction")
            return extract_qa_smart_fallback(df)

        # Define structured response model
        class QAPair(BaseModel):
            question: str = Field(..., description="The question or requirement text")
            answer: str = Field(..., description="The answer or response text")

        class RFPAnalysis(BaseModel):
            question_column: str = Field(..., description="Name of the column containing questions")
            answer_column: str = Field(..., description="Name of the column containing answers")
            qa_pairs: List[QAPair] = Field(..., description="List of extracted question-answer pairs")

        # Convert sample data for analysis
        sample_size = min(5, len(df))
        sample_data = []

        for i in range(sample_size):
            row_data = {}
            for col in df.columns:
                if pd.notna(df.iloc[i][col]):
                    row_data[col] = str(df.iloc[i][col])
            sample_data.append(row_data)

        # Create specialized RFP extraction agent with structured output
        rfp_agent = Agent(
            name="RFP Q&A Extractor",
            model=OpenAIChat(id="gpt-4o-mini"),
            description="Expert at analyzing Excel/spreadsheet data to extract question-answer pairs from RFPs.",
            instructions=[
                "Analyze the provided Excel data to identify question and answer columns.",
                "Look for patterns: questions often end with '?', contain words like 'Can', 'Do', 'What', 'How'.",
                "Answers typically contain responses, solutions, capabilities, or explanations.",
                "Extract ALL valid Q&A pairs from the data, not just the sample.",
                "Be thorough and accurate in your analysis.",
            ],
            response_model=RFPAnalysis,
            use_json_mode=True,
        )

        # Create analysis prompt
        prompt = f"""
Analyze this Excel data to extract question-answer pairs from an RFP document:

Available columns: {list(df.columns)}
Total rows in dataset: {len(df)}

Sample data (first {sample_size} rows):
{json.dumps(sample_data, indent=2)}

Your task:
1. Identify which column contains questions/requirements
2. Identify which column contains answers/responses
3. Extract all Q&A pairs from the entire dataset

Return the analysis with the identified columns and all extracted Q&A pairs.
"""

        # Get AI response with structured output
        response = rfp_agent.run(prompt, stream=False)

        # Extract the structured response
        if hasattr(response, 'content') and isinstance(response.content, RFPAnalysis):
            analysis = response.content

            # Validate that the identified columns exist
            if (analysis.question_column in df.columns and
                analysis.answer_column in df.columns):

                # Extract all Q&A pairs from the full dataset using identified columns
                qa_pairs = []
                for _, row in df.iterrows():
                    if (pd.notna(row[analysis.question_column]) and
                        pd.notna(row[analysis.answer_column])):
                        qa_pairs.append({
                            'question': str(row[analysis.question_column]).strip(),
                            'answer': str(row[analysis.answer_column]).strip()
                        })

                print(f"✅ LLM identified columns: '{analysis.question_column}' → '{analysis.answer_column}'")
                print(f"✅ Extracted {len(qa_pairs)} Q&A pairs using LLM analysis")
                return qa_pairs

        print("❌ LLM analysis failed, using fallback extraction")
        return extract_qa_smart_fallback(df)

    except Exception as e:
        print(f"❌ LLM extraction failed: {e}")
        return extract_qa_smart_fallback(df)


def extract_qa_smart_fallback(df):
    """
    Smart fallback extraction without complex rules.
    """
    qa_pairs = []

    # Simple heuristic: look for columns that might be Q&A
    if len(df.columns) >= 2:
        # Use first two columns as Q&A
        col1, col2 = df.columns[0], df.columns[1]

        for _, row in df.iterrows():
            if pd.notna(row[col1]) and pd.notna(row[col2]):
                q = str(row[col1]).strip()
                a = str(row[col2]).strip()

                # Basic validation - skip if too short or looks like headers
                if len(q) > 10 and len(a) > 10 and not q.lower() in ['question', 'questions', 'q']:
                    qa_pairs.append({
                        'question': q,
                        'answer': a
                    })

    return qa_pairs


async def extract_questions_only(df):
    """
    Extract only questions from Excel file for response generation mode.
    Uses LLM to intelligently identify the RFP column.
    """
    questions = []

    # Use LLM to identify which column contains RFP questions/requirements
    try:
        from agno.agent import Agent
        from agno.models.openai import OpenAIChat

        # Create column analysis agent
        column_agent = Agent(
            name="RFP Column Identifier",
            model=OpenAIChat(id="gpt-4o-mini"),
            description="Expert at identifying which column in Excel data contains RFP questions or requirements.",
            instructions=[
                "Analyze the Excel columns and their sample data.",
                "Identify which column contains RFP questions, requirements, or specifications.",
                "Look for columns with questions, numbered requirements, technical specifications, or vendor requirements.",
                "Return only the column name that contains the main RFP content."
            ]
        )

        # Prepare column analysis data
        column_info = {}
        for col in df.columns:
            sample_data = df[col].dropna().head(5).tolist()
            column_info[col] = [str(item)[:200] for item in sample_data]  # Limit length

        prompt = f"""
        Analyze these Excel columns and identify which one contains RFP questions or requirements:

        Available columns and their sample data:
        {column_info}

        Which column contains the RFP questions/requirements? Return only the column name.
        """

        response = column_agent.run(prompt)
        identified_column = response.content.strip().strip('"\'')

        # Validate the identified column exists
        if identified_column in df.columns:
            best_column = identified_column
        else:
            # Fallback to first column if LLM response is invalid
            best_column = df.columns[0] if len(df.columns) > 0 else None

    except Exception as e:
        print(f"LLM column identification failed: {e}")
        # Fallback to first column
        best_column = df.columns[0] if len(df.columns) > 0 else None

    # Extract all content from the identified column
    if best_column:
        current_question = ""

        for _, row in df.iterrows():
            if pd.notna(row[best_column]):
                text = str(row[best_column]).strip()

                if len(text) < 5:  # Skip very short content
                    continue

                # Check if this looks like a new numbered item
                import re
                if re.match(r'^\d+\.?\s+', text):
                    # Save previous question if we have one
                    if current_question and len(current_question.strip()) > 10:
                        questions.append({
                            'question': current_question.strip(),
                            'answer': ''
                        })
                    # Start new question
                    current_question = text
                elif current_question and len(text) > 5:
                    # This might be a continuation of the previous question
                    current_question += " " + text
                else:
                    # This is a standalone question/requirement
                    if len(text) > 10:
                        questions.append({
                            'question': text,
                            'answer': ''
                        })

        # Don't forget the last question
        if current_question and len(current_question.strip()) > 10:
            questions.append({
                'question': current_question.strip(),
                'answer': ''
            })

    return questions


@router.post("/upload", response_model=RFPDocumentListItem)
async def upload_rfp_document(
    file: UploadFile = File(...),
    purpose: str = Form(...),
    customer_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload an RFP document (Excel/PDF) for processing."""

    # Validate purpose
    allowed_purposes = ['analyze', 'respond']
    if purpose not in allowed_purposes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid purpose. Allowed values: {', '.join(allowed_purposes)}"
        )

    # Validate file type
    allowed_extensions = ['.xlsx', '.xls', '.pdf']
    file_extension = '.' + file.filename.split('.')[-1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    # Create RFP document record
    rfp_doc = RFPDocument(
        filename=file.filename,
        customer_id=customer_id,
        processed_status=ProcessedStatus.PENDING,
        business_context={
            "upload_time": datetime.utcnow().isoformat(),
            "purpose": purpose
        }
    )

    db.add(rfp_doc)
    await db.commit()
    await db.refresh(rfp_doc)
    
    # Save file temporarily for processing
    file_content = await file.read()
    
    # Process file in background
    background_tasks.add_task(
        process_rfp_file,
        rfp_doc.id,
        file_content,
        file_extension,
        purpose
    )
    
    return rfp_doc


async def process_rfp_file(
    document_id: UUID,
    file_content: bytes,
    file_extension: str,
    purpose: str
):
    """Process RFP file and extract Q&A pairs."""

    from app.core.database import AsyncSessionLocal

    rfp_processor = RFPProcessor()

    async with AsyncSessionLocal() as db:
        try:
            # Update status to processing
            result = await db.execute(select(RFPDocument).filter(RFPDocument.id == document_id))
            doc = result.scalar_one_or_none()
            if not doc:
                return

            doc.processed_status = ProcessedStatus.PROCESSING
            await db.commit()

            qa_pairs = []

            if file_extension in ['.xlsx', '.xls']:
                # Process Excel file with LLM-based extraction
                df = pd.read_excel(io.BytesIO(file_content))

                if purpose == 'respond':
                    # For response mode, extract only questions
                    qa_pairs = await extract_questions_only(df)
                else:
                    # For analysis mode, extract full Q&A pairs
                    qa_pairs = await extract_qa_with_llm(df)

            # Update document with total questions
            doc.total_questions = len(qa_pairs)
            doc.processed_questions = 0
            await db.commit()

            # Process each Q&A pair
            for idx, qa in enumerate(qa_pairs):
                # Create Q&A pair record
                qa_pair = RFPQAPair(
                    document_id=document_id,
                    question=qa['question'],
                    answer=qa['answer'],
                    customer_context={"index": idx, "purpose": purpose}
                )

                # Only do feature linking for analysis mode
                if purpose == 'analyze':
                    # Generate embedding for Q&A
                    text_for_embedding = f"{qa['question']} {qa['answer']}"
                    embedding = await embedding_service.generate_embedding(text_for_embedding)

                    # Find similar features
                    similar_features = await rfp_processor.find_similar_features(
                        embedding,
                        threshold=0.7,  # Lower threshold for better matching
                        db=db
                    )

                    # Handle feature linking or creation
                    if similar_features:
                        # Link to most similar existing feature
                        best_feature, similarity_score = similar_features[0]
                        qa_pair.feature_id = best_feature.id
                        qa_pair.customer_context["similarity_score"] = float(similarity_score)
                        qa_pair.customer_context["matched_feature"] = best_feature.title

                        # Update feature request count
                        best_feature.customer_request_count += 1
                    else:
                        # Create new feature if no similar features found
                        new_feature = await rfp_processor._create_feature_from_qa(
                            qa_pair,
                            doc.customer_id,  # Pass the actual customer_id from document
                            db
                        )
                        qa_pair.feature_id = new_feature.id
                        qa_pair.customer_context["feature_created"] = True
                        qa_pair.customer_context["new_feature_title"] = new_feature.title

                db.add(qa_pair)

                # Update processed count
                doc.processed_questions = idx + 1

                if (idx + 1) % 10 == 0:  # Commit every 10 records
                    await db.commit()

            # Final commit and status update
            doc.processed_status = ProcessedStatus.COMPLETE
            await db.commit()

        except Exception as e:
            # Update status to failed
            result = await db.execute(select(RFPDocument).filter(RFPDocument.id == document_id))
            doc = result.scalar_one_or_none()
            doc.processed_status = ProcessedStatus.FAILED
            doc.business_context = doc.business_context or {}
            doc.business_context['error'] = str(e)
            await db.commit()
            raise


@router.get("/{document_id}", response_model=RFPDocumentResponse)
async def get_rfp_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific RFP document by ID."""

    result = await db.execute(
        select(RFPDocument)
        .options(selectinload(RFPDocument.qa_pairs))
        .filter(RFPDocument.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFP document not found"
        )

    return doc


@router.get("/", response_model=RFPDocumentListResponse)
async def list_rfp_documents(
    skip: int = 0,
    limit: int = 20,
    customer_id: Optional[UUID] = None,
    status: Optional[ProcessedStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all RFP documents with optional filtering."""

    query = select(RFPDocument)

    if customer_id:
        query = query.filter(RFPDocument.customer_id == customer_id)

    if status:
        query = query.filter(RFPDocument.processed_status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get items with pagination
    items_query = query.offset(skip).limit(limit)
    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    # Calculate pagination info
    page = (skip // limit) + 1
    pages = (total + limit - 1) // limit  # Ceiling division

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": limit,
        "pages": pages
    }


@router.get("/{document_id}/qa-pairs", response_model=List[RFPQAPairResponse])
async def get_document_qa_pairs(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all Q&A pairs for a specific RFP document with feature details."""

    result = await db.execute(
        select(RFPQAPair)
        .options(selectinload(RFPQAPair.feature))
        .filter(RFPQAPair.document_id == document_id)
    )
    qa_pairs = result.scalars().all()

    return qa_pairs


@router.post("/process", response_model=RFPProcessingResponse)
async def process_rfp_document(
    request: RFPProcessingRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Process an uploaded RFP document."""

    result = await db.execute(select(RFPDocument).filter(RFPDocument.id == request.document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFP document not found"
        )
    
    # Create processor instance
    rfp_processor = RFPProcessor()
    
    # Add processing task
    background_tasks.add_task(
        rfp_processor.process_document,
        request.document_id,
        auto_link_features=request.auto_link_features,
        extract_business_context=request.extract_business_context,
        generate_feature_suggestions=request.generate_feature_suggestions,
        db=db
    )
    
    return {
        "document_id": request.document_id,
        "processing_id": request.document_id,  # Using same ID for simplicity
        "status": ProcessedStatus.PROCESSING
    }


@router.post("/analyze", response_model=RFPAnalysisResponse)
async def analyze_rfps(
    request: RFPAnalysisRequest,
    db: AsyncSession = Depends(get_db)
):
    """Analyze RFP documents to extract insights."""

    # This would typically be a more complex analysis
    query = select(RFPDocument)

    if request.customer_id:
        query = query.filter(RFPDocument.customer_id == request.customer_id)

    if request.document_ids:
        query = query.filter(RFPDocument.id.in_(request.document_ids))

    result = await db.execute(query)
    documents = result.scalars().all()
    
    # Basic analysis (would be enhanced with actual analytics)
    total_qa_pairs = sum(doc.total_questions or 0 for doc in documents)
    
    return {
        "analysis_id": UUID("12345678-1234-5678-1234-567812345678"),  # Mock ID
        "documents_analyzed": len(documents),
        "total_qa_pairs": total_qa_pairs,
        "features_mentioned": 0,  # Would be calculated
        "most_requested_features": [],
        "feature_gaps": [],
        "customer_segments_represented": [],
        "geographic_distribution": {},
        "emerging_trends": [],
        "technology_keywords": []
    }


@router.delete("/{document_id}")
async def delete_rfp_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Delete an RFP document and all associated Q&A pairs."""

    result = await db.execute(select(RFPDocument).filter(RFPDocument.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RFP document not found"
        )

    await db.delete(doc)
    await db.commit()

    return {"message": "RFP document deleted successfully"}


@router.post("/{document_id}/generate-responses")
async def generate_rfp_responses(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Generate RFP responses using the knowledge base search tool."""

    try:
        # Get the RFP document and its Q&A pairs
        result = await db.execute(
            select(RFPDocument).filter(RFPDocument.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(status_code=404, detail="RFP document not found")

        # Get Q&A pairs
        result = await db.execute(
            select(RFPQAPair).filter(RFPQAPair.document_id == document_id)
        )
        qa_pairs = result.scalars().all()

        if not qa_pairs:
            raise HTTPException(status_code=400, detail="No Q&A pairs found for this document")

        # Import Agno components for response generation
        from agno.agent import Agent
        from agno.models.openai import OpenAIChat
        from pydantic import BaseModel, Field
        from typing import List
        import os

        # Check if OpenAI API key is available
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        # Define response model
        class RFPResponse(BaseModel):
            question: str = Field(..., description="The original question")
            suggested_answer: str = Field(..., description="The generated answer based on knowledge base")
            confidence: str = Field(..., description="Confidence level: High, Medium, or Low")
            sources_used: List[str] = Field(default_factory=list, description="Knowledge base sources referenced")

        class RFPResponseSet(BaseModel):
            responses: List[RFPResponse] = Field(..., description="List of generated responses")

        # Create RFP response agent
        rfp_response_agent = Agent(
            name="RFP Response Generator",
            model=OpenAIChat(id="gpt-4o-mini"),
            tools=[search_knowledge_base],
            description="Expert at generating professional RFP responses using company knowledge base.",
            instructions=[
                "You are an expert RFP response generator for OneLens.",
                "For each question, search the knowledge base to find relevant information.",
                "Generate professional, accurate, and compelling responses.",
                "Always indicate your confidence level based on available information.",
                "If you can't find relevant information, be honest about limitations.",
                "Focus on capabilities, features, and benefits that OneLens provides.",
                "Keep responses concise but comprehensive.",
                "Use a professional, confident tone suitable for business proposals.",
            ],
            response_model=RFPResponseSet,
            use_json_mode=True,
        )

        # Prepare questions for the agent
        questions = [qa.question for qa in qa_pairs]
        questions_text = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])

        # Generate responses
        prompt = f"""
Generate professional RFP responses for the following questions about OneLens:

{questions_text}

For each question:
1. Search the knowledge base for relevant information
2. Generate a professional, compelling response
3. Indicate confidence level (High/Medium/Low) based on available information
4. Note which sources were used

Focus on OneLens capabilities, features, and benefits. Be honest about limitations if information is not available.
"""

        # Get AI response
        response = rfp_response_agent.run(prompt, stream=False)

        # Extract the structured response
        if hasattr(response, 'content') and isinstance(response.content, RFPResponseSet):
            generated_responses = response.content.responses

            # Format the response
            response_data = {
                "document_id": document_id,
                "total_questions": len(questions),
                "responses_generated": len(generated_responses),
                "responses": []
            }

            for i, resp in enumerate(generated_responses):
                response_data["responses"].append({
                    "question_id": qa_pairs[i].id if i < len(qa_pairs) else None,
                    "question": resp.question,
                    "suggested_answer": resp.suggested_answer,
                    "confidence": resp.confidence,
                    "sources_used": resp.sources_used
                })

            return response_data

        else:
            raise HTTPException(status_code=500, detail="Failed to generate responses")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating responses: {str(e)}")


@router.delete("/admin/clear-all")
async def clear_all_rfp_data(db: AsyncSession = Depends(get_db)):
    """Clear all RFP documents and related data for testing purposes."""

    try:
        # Delete all Q&A pairs first (due to foreign key constraints)
        await db.execute(text("DELETE FROM rfp_qa_pairs"))

        # Delete all RFP documents
        await db.execute(text("DELETE FROM rfp_documents"))

        await db.commit()

        return {"message": "All RFP data cleared successfully"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error clearing data: {str(e)}")