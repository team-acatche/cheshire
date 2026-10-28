"""tests for user asserted rules in evaluation pipeline."""

from unittest.mock import MagicMock, patch
import pytest
from haystack import Document
from haystack_integrations.document_stores.qdrant import QdrantDocumentStore

from knowledge_base.qdrant import QdrantKnowledgeRepository
from knowledge_base.repository import KnowledgeRepository
from cheshire_configs.preprocessors.multistep.pipelines import (
    classify_rule_nature,
    _load_user_asserted_rules,
    build_pass1_system_prompt,
    build_global_audit_system_prompt,
    build_evaluation_pipeline,
    build_global_audit_pipeline,
)


class TestClassifyRuleNature:
    # test classification of global document-level rules
    def test_global_rules_classified_as_global(self):
        global_samples = [
            "The document must contain an Architecture Overview",
            "The document must include Disaster Recovery Procedures",
            "The document must contain a Deployment Diagram",
            "Architecture Diagram should exist",
            "Product Design Document should be present as a Reference Document",
            "The document must contain a Data Dictionary under Processing Specifications",
        ]
        for rule in global_samples:
            assert classify_rule_nature(rule) == "global", f"expected {rule} to be global"

    # test classification of local section-level rules
    def test_local_rules_classified_as_local(self):
        local_samples = [
            "All passwords must be hashed with Argon2id",
            "REST APIs must use TLS 1.3",
            "Database credentials should not be hardcoded",
            "The Estimates section must include QA Testing phase",
            "Session timeouts must not exceed 15 minutes",
            "Flowcharts must not use diagonal lines",
        ]
        for rule in local_samples:
            assert classify_rule_nature(rule) == "local", f"expected {rule} to be local"


class TestLoadUserAssertedRules:
    # test querying user_asserted source filter
    def test_queries_with_user_asserted_filter(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="All passwords must be hashed", meta={"source": "user_asserted"})
        ]

        rules = _load_user_asserted_rules(knowledge_repo=mock_repo)

        mock_repo.query.assert_called_once()
        filters = mock_repo.query.call_args.kwargs.get("filters")
        assert filters["field"] == "meta.source"
        assert filters["operator"] == "=="
        assert filters["value"] == "user_asserted"
        assert rules == ["All passwords must be hashed"]

    # test filtering by local nature
    def test_filters_by_nature_local(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="All passwords must be hashed with Argon2id", meta={"source": "user_asserted"}),
            Document(content="The document must contain an Architecture Overview", meta={"source": "user_asserted"}),
        ]

        local_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="local")
        assert local_rules == ["All passwords must be hashed with Argon2id"]

    # test filtering by global nature
    def test_filters_by_nature_global(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="All passwords must be hashed with Argon2id", meta={"source": "user_asserted"}),
            Document(content="The document must contain an Architecture Overview", meta={"source": "user_asserted"}),
        ]

        global_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="global")
        assert global_rules == ["The document must contain an Architecture Overview"]

    # test duplicate removal
    def test_deduplicates_rules(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="Rule A", meta={"source": "user_asserted"}),
            Document(content="Rule A", meta={"source": "user_asserted"}),
            Document(content="Rule B", meta={"source": "user_asserted"}),
        ]

        rules = _load_user_asserted_rules(knowledge_repo=mock_repo)
        assert rules == ["Rule A", "Rule B"]

    # test explicit meta rule_nature takes precedence over content classifier
    def test_prefers_meta_rule_nature_over_classifier(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            # content looks local, but meta explicitly marks it global
            Document(
                content="All passwords must be hashed with Argon2id",
                meta={"source": "user_asserted", "rule_nature": "global"},
            ),
        ]

        global_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="global")
        local_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="local")
        assert global_rules == ["All passwords must be hashed with Argon2id"]
        assert local_rules == []

    # test backward compatibility: falls back to classifier when rule_nature meta is missing
    def test_falls_back_to_classifier_when_meta_rule_nature_missing(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            # legacy document without rule_nature field
            Document(
                content="The document must contain an Architecture Overview",
                meta={"source": "user_asserted"},
            ),
            Document(
                content="All passwords must be hashed with Argon2id",
                meta={"source": "user_asserted"},
            ),
        ]

        global_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="global")
        local_rules = _load_user_asserted_rules(knowledge_repo=mock_repo, rule_nature="local")
        assert global_rules == ["The document must contain an Architecture Overview"]
        assert local_rules == ["All passwords must be hashed with Argon2id"]


class TestEvaluationPromptsWithUserAssertedRules:
    # test pass1 prompt includes user asserted local rule
    def test_pass1_prompt_includes_user_asserted_local_rule(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="All passwords must be hashed with Argon2id", meta={"source": "user_asserted"}),
            Document(content="The document must contain an Architecture Overview", meta={"source": "user_asserted"}),
        ]

        prompt = build_pass1_system_prompt(knowledge_repo=mock_repo)

        assert "MANDATORY LOCAL STANDARDS CHECKLIST:" in prompt
        assert "- All passwords must be hashed with Argon2id" in prompt
        assert "Architecture Overview" not in prompt

    # test pass2 global audit prompt includes user asserted global rule
    def test_global_audit_prompt_includes_user_asserted_global_rule(self):
        mock_repo = MagicMock(spec=KnowledgeRepository)
        mock_repo.query.return_value = [
            Document(content="All passwords must be hashed with Argon2id", meta={"source": "user_asserted"}),
            Document(content="The document must contain an Architecture Overview", meta={"source": "user_asserted"}),
        ]

        prompt = build_global_audit_system_prompt(knowledge_repo=mock_repo)

        assert "MANDATORY GLOBAL STANDARDS CHECKLIST:" in prompt
        assert "- The document must contain an Architecture Overview" in prompt
        assert "Argon2id" not in prompt

    # test evaluation fails if qdrant is not running and repo is None
    def test_evaluation_fails_when_qdrant_unavailable(self):
        with patch(
            "knowledge_base.qdrant.QdrantRepositoryManager.get_repositories",
            side_effect=ConnectionError("qdrant connection refused"),
        ):
            with pytest.raises(ConnectionError):
                build_pass1_system_prompt(knowledge_repo=None)

            with pytest.raises(ConnectionError):
                build_global_audit_system_prompt(knowledge_repo=None)


class TestInMemoryQdrantRuleIntegration:
    @pytest.fixture
    def in_memory_knowledge_repo(self):
        # in memory qdrant for test without live server
        store = QdrantDocumentStore(
            location=":memory:",
            index="test_user_asserted",
            embedding_dim=384,
        )
        return QdrantKnowledgeRepository.create(store)

    # test in-memory qdrant document saving and prompt building
    def test_in_memory_qdrant_user_asserted_rules_in_prompts(self, in_memory_knowledge_repo):
        repo = in_memory_knowledge_repo

        # save user asserted facts
        docs = [
            Document(
                id="doc-local",
                content="All passwords must be hashed with Argon2id",
                meta={"source": "user_asserted", "is_global": True},
            ),
            Document(
                id="doc-global",
                content="The document must contain an Architecture Overview",
                meta={"source": "user_asserted", "is_global": True},
            ),
            Document(
                id="doc-seeded",
                content="Seeded company standard",
                meta={"source": "global_rules.json", "is_global": True},
            ),
        ]
        repo.save(docs)

        # verify pass1 prompt has local user asserted rule
        pass1_prompt = build_pass1_system_prompt(knowledge_repo=repo)
        assert "- All passwords must be hashed with Argon2id" in pass1_prompt
        assert "Architecture Overview" not in pass1_prompt
        assert "Seeded company standard" not in pass1_prompt

        # verify global audit prompt has global user asserted rule
        pass2_prompt = build_global_audit_system_prompt(knowledge_repo=repo)
        assert "- The document must contain an Architecture Overview" in pass2_prompt
        assert "Argon2id" not in pass2_prompt
        assert "Seeded company standard" not in pass2_prompt

