from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from apps.authentication.permissions import HasValidTenant
from .serializers import RagQueryInputSerializer, RagQueryOutputSerializer
from .services.rag_service import RagQueryService


class RagQueryView(APIView):
    """
    POST /api/v1/query/
    Enterprise Agentic RAG Question Answering Endpoint.

    Workflow:
    1. Authenticates request via API Key and isolates tenant.
    2. Validates query input.
    3. Executes vector similarity search in Pinecone filtered strictly by tenant_id.
    4. Formulates MCP prompt with grounded context.
    5. Invokes LLM and returns synthesized response with document citations.
    """
    permission_classes = [HasValidTenant]

    def post(self, request, *args, **kwargs):
        input_serializer = RagQueryInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        query = input_serializer.validated_data['query']
        top_k = input_serializer.validated_data.get('top_k', 4)
        document_id = input_serializer.validated_data.get('document_id')
        tenant_id = str(request.tenant.id)

        rag_service = RagQueryService()
        result = rag_service.execute_query(
            tenant_id=tenant_id,
            query=query,
            top_k=top_k,
            document_id=str(document_id) if document_id else None
        )

        output_serializer = RagQueryOutputSerializer(result)
        return Response(output_serializer.data, status=status.HTTP_200_OK)
