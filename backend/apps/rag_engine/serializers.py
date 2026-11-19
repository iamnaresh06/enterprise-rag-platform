from rest_framework import serializers


class RagQueryInputSerializer(serializers.Serializer):
    """
    Validates user query input for Agentic RAG semantic retrieval.
    """
    query = serializers.CharField(
        required=True,
        min_length=2,
        max_length=1500,
        trim_whitespace=True,
        help_text="Natural language question to query against tenant private documentation"
    )
    top_k = serializers.IntegerField(
        required=False,
        default=4,
        min_value=1,
        max_value=10,
        help_text="Maximum number of relevant context chunks to retrieve (default: 4)"
    )
    document_id = serializers.UUIDField(
        required=False,
        default=None,
        allow_null=True,
        help_text="Optional document UUID to filter search strictly to a single document"
    )


class CitationSerializer(serializers.Serializer):
    document_id = serializers.UUIDField(allow_null=True)
    filename = serializers.CharField()
    chunk_index = serializers.IntegerField()
    similarity_score = serializers.FloatField()
    snippet = serializers.CharField()


class RagQueryOutputSerializer(serializers.Serializer):
    answer = serializers.CharField()
    citations = CitationSerializer(many=True)
    retrieved_chunk_count = serializers.IntegerField()
    latency_ms = serializers.FloatField()
    tenant_id = serializers.CharField()
