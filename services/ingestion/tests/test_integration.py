"""Integration test for ingestion service."""
import pytest
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from config import IngestionConfig
from orchestrator import IngestionOrchestrator


@pytest.fixture
def config():
    """Create configuration from environment."""
    return IngestionConfig.from_env()


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS env var"
)
class TestIngestionIntegration:
    """Integration tests for ingestion service."""

    def test_full_ingestion_single_station(self, config):
        """Test ingesting a single station."""
        orchestrator = IngestionOrchestrator(config)
        
        try:
            # Ingest air temperature for one station
            stats = orchestrator.ingest_variable(
                variable="air_temperature",
                station_ids=["00433"],  # Berlin-Dahlem
                recent=False,
                skip_existing=True,
            )
            
            assert stats['total_stations'] >= 1
            assert stats['processed'] + stats['skipped'] + stats['failed'] == stats['total_stations']
            
        finally:
            orchestrator.close()

    def test_metadata_tracking(self, config):
        """Test that metadata is properly tracked."""
        orchestrator = IngestionOrchestrator(config)
        
        try:
            run_id = orchestrator.registry.create_ingestion_run("test_variable")
            
            # Verify run was created
            run_details = orchestrator.registry.get_ingestion_run(run_id)
            assert run_details is not None
            assert run_details['variable'] == "test_variable"
            assert run_details['status'] == "running"
            
            # Update run
            orchestrator.registry.update_ingestion_run(
                run_id=run_id,
                status="completed",
                station_count=1,
            )
            
            # Verify update
            run_details = orchestrator.registry.get_ingestion_run(run_id)
            assert run_details['status'] == "completed"
            assert run_details['station_count'] == 1
            
        finally:
            orchestrator.close()
