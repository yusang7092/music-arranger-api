from supabase import create_client, Client
from app.core.config import settings


def get_supabase_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)


# 모듈 로드 시가 아닌, 첫 사용 시 초기화
class _LazySupabase:
    _client: Client | None = None

    def __getattr__(self, name):
        if self._client is None:
            self._client = get_supabase_client()
        return getattr(self._client, name)


supabase: Client = _LazySupabase()  # type: ignore
