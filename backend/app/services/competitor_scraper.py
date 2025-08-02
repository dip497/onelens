from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
import asyncio
import aiohttp
from bs4 import BeautifulSoup

from app.core.database import get_db
from app.models import Competitor, CompetitorFeature, CompetitorScrapingJob
from app.models.enums import ScrapingJobType, ScrapingJobStatus, AvailabilityStatus


class CompetitorScraper:
    """Service for scraping competitor websites and extracting information"""
    
    async def scrape_competitor(
        self,
        competitor_id: UUID,
        job_id: UUID,
        job_type: ScrapingJobType,
        target_urls: Optional[List[str]] = None
    ):
        """Main method to scrape competitor data"""
        async for db in get_db():
            try:
                # Update job status to running
                await self._update_job_status(db, job_id, ScrapingJobStatus.RUNNING)
                
                # Get competitor details
                competitor = await db.get(Competitor, competitor_id)
                if not competitor:
                    raise ValueError(f"Competitor {competitor_id} not found")
                
                # Determine URLs to scrape
                urls = target_urls or []
                if not urls and competitor.website:
                    urls = [competitor.website]
                
                # Perform scraping based on job type
                results = {}
                if job_type == ScrapingJobType.FEATURES:
                    results = await self._scrape_features(competitor, urls)
                elif job_type == ScrapingJobType.PRICING:
                    results = await self._scrape_pricing(competitor, urls)
                elif job_type == ScrapingJobType.NEWS:
                    results = await self._scrape_news(competitor, urls)
                elif job_type == ScrapingJobType.REVIEWS:
                    results = await self._scrape_reviews(competitor, urls)
                elif job_type == ScrapingJobType.FULL_SCAN:
                    results = await self._full_scan(competitor, urls)
                
                # Save results to database
                await self._save_results(db, competitor_id, results)
                
                # Update job status to completed
                await self._update_job_status(
                    db, job_id, ScrapingJobStatus.COMPLETED, results=results
                )
                
            except Exception as e:
                # Update job status to failed
                await self._update_job_status(
                    db, job_id, ScrapingJobStatus.FAILED, error_message=str(e)
                )
    
    async def _update_job_status(
        self,
        db,
        job_id: UUID,
        status: ScrapingJobStatus,
        results: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """Update scraping job status"""
        job = await db.get(CompetitorScrapingJob, job_id)
        if job:
            job.status = status
            if status == ScrapingJobStatus.RUNNING:
                job.started_at = datetime.utcnow()
            elif status in [ScrapingJobStatus.COMPLETED, ScrapingJobStatus.FAILED]:
                job.completed_at = datetime.utcnow()
            if results:
                job.results = results
            if error_message:
                job.error_message = error_message
            await db.commit()
    
    async def _fetch_page(self, url: str) -> str:
        """Fetch HTML content from a URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                return await response.text()
    
    async def _scrape_features(
        self,
        competitor: Competitor,
        urls: List[str]
    ) -> Dict[str, Any]:
        """Scrape product features from competitor website"""
        features = []
        
        for url in urls:
            try:
                html = await self._fetch_page(url)
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for common feature patterns
                # TODO: Implement more sophisticated feature extraction
                feature_sections = soup.find_all(['section', 'div'], class_=['features', 'feature-list'])
                
                for section in feature_sections:
                    feature_items = section.find_all(['li', 'div', 'article'])
                    for item in feature_items:
                        title = item.find(['h2', 'h3', 'h4'])
                        description = item.find(['p', 'span'])
                        
                        if title:
                            features.append({
                                "name": title.get_text(strip=True),
                                "description": description.get_text(strip=True) if description else "",
                                "source_url": url
                            })
                
            except Exception as e:
                print(f"Error scraping {url}: {e}")
        
        return {"features": features, "urls_scraped": urls}
    
    async def _scrape_pricing(
        self,
        competitor: Competitor,
        urls: List[str]
    ) -> Dict[str, Any]:
        """Scrape pricing information from competitor website"""
        pricing_data = []
        
        # TODO: Implement pricing scraping logic
        # Look for pricing tables, subscription tiers, etc.
        
        return {"pricing": pricing_data, "urls_scraped": urls}
    
    async def _scrape_news(
        self,
        competitor: Competitor,
        urls: List[str]
    ) -> Dict[str, Any]:
        """Scrape news and updates from competitor website"""
        news_items = []
        
        # TODO: Implement news scraping logic
        # Look for blog posts, press releases, etc.
        
        return {"news": news_items, "urls_scraped": urls}
    
    async def _scrape_reviews(
        self,
        competitor: Competitor,
        urls: List[str]
    ) -> Dict[str, Any]:
        """Scrape reviews and testimonials"""
        reviews = []
        
        # TODO: Implement review scraping logic
        # Could integrate with review platforms APIs
        
        return {"reviews": reviews, "urls_scraped": urls}
    
    async def _full_scan(
        self,
        competitor: Competitor,
        urls: List[str]
    ) -> Dict[str, Any]:
        """Perform a comprehensive scan of all data types"""
        results = {}
        
        # Run all scraping methods
        results["features"] = await self._scrape_features(competitor, urls)
        results["pricing"] = await self._scrape_pricing(competitor, urls)
        results["news"] = await self._scrape_news(competitor, urls)
        results["reviews"] = await self._scrape_reviews(competitor, urls)
        
        return results
    
    async def _save_results(
        self,
        db,
        competitor_id: UUID,
        results: Dict[str, Any]
    ):
        """Save scraped results to the database"""
        # Save features if found
        if "features" in results and results["features"].get("features"):
            for feature_data in results["features"]["features"]:
                # Check if feature already exists
                existing = await db.query(CompetitorFeature).filter(
                    CompetitorFeature.competitor_id == competitor_id,
                    CompetitorFeature.feature_name == feature_data["name"]
                ).first()
                
                if existing:
                    # Update existing feature
                    existing.feature_description = feature_data["description"]
                    existing.source_url = feature_data["source_url"]
                    existing.last_verified = datetime.utcnow()
                else:
                    # Create new feature
                    new_feature = CompetitorFeature(
                        competitor_id=competitor_id,
                        feature_name=feature_data["name"],
                        feature_description=feature_data["description"],
                        source_url=feature_data["source_url"],
                        availability=AvailabilityStatus.AVAILABLE,
                        last_verified=datetime.utcnow()
                    )
                    db.add(new_feature)
            
            await db.commit()