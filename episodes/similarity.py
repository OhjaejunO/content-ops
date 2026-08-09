"""Topic 유사도 판정.

무거운 의존성(sentence-transformers, torch)은 이 모듈 안에서 지연 임포트한다.
기본 설치만으로 앱 전체가 뜨고, 임베딩이 필요한 순간에만 없으면 안내가 나가야
하기 때문이다. 유사도 계산 자체는 표준 라이브러리만 쓰므로 모델 없이도 검증된다.
"""

import hashlib
import math
from array import array

#: 다국어 모델. 소재가 한국어와 영어에 섞여 들어오므로 둘 다 되는 것을 쓴다.
MODEL_NAME = 'BAAI/bge-m3'

#: 벡터를 float32로 직렬화한다. 이 규모(Topic 수십 개)에서 배정밀도는 의미가 없다.
VECTOR_TYPECODE = 'f'

_model = None


class EmbeddingUnavailable(RuntimeError):
    """임베딩 의존성이 설치되지 않았을 때."""


def encode_vector(values):
    """실수 리스트를 BinaryField에 넣을 bytes로."""
    return array(VECTOR_TYPECODE, values).tobytes()


def decode_vector(blob):
    """bytes를 실수 리스트로."""
    vector = array(VECTOR_TYPECODE)
    vector.frombytes(bytes(blob))
    return list(vector)


def cosine_similarity(left, right):
    """두 벡터의 코사인 유사도. 길이가 다르거나 영벡터면 0.0."""
    if len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    return dot / (left_norm * right_norm)


def topic_text(topic):
    """Topic을 임베딩할 문자열. 사건 이름과 그 사건을 다룬 제목들을 합친다.

    이름만으로는 표현이 짧아 비슷한 사건이 잘 구분되지 않는다. 실제로 그
    사건을 어떤 말로 다뤘는지가 붙어야 판정이 쓸 만해진다.
    """
    titles = topic.episodes.order_by('number').values_list('title', flat=True)
    return ' / '.join([topic.name, *titles])


def cache_key(text):
    """임베딩 캐시 무효화용 키. 모델이 바뀌어도 다시 계산되도록 같이 넣는다."""
    return hashlib.sha256(f'{MODEL_NAME}\n{text}'.encode('utf-8')).hexdigest()


def resolve_device():
    """GPU가 있으면 쓰고 없으면 CPU."""
    try:
        import torch
    except ImportError:
        return 'cpu'
    return 'cuda' if torch.cuda.is_available() else 'cpu'


def load_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingUnavailable(
                '임베딩 의존성이 설치되지 않았습니다.\n'
                '  pip install -r requirements-ml.txt\n'
                '기본 설치에는 포함되지 않는 선택 의존성입니다.'
            ) from exc
        _model = SentenceTransformer(MODEL_NAME, device=resolve_device())
    return _model


def embed_texts(texts):
    """문자열들을 벡터 리스트로. 테스트는 이 함수를 mock한다."""
    vectors = load_model().encode(list(texts), normalize_embeddings=True)
    return [[float(value) for value in vector] for vector in vectors]


def refresh_topic_embeddings(topics, refresh=False):
    """임베딩이 없거나 입력 텍스트가 바뀐 Topic만 다시 인코딩해 저장한다."""
    stale = []
    for topic in topics:
        text = topic_text(topic)
        key = cache_key(text)
        if refresh or not topic.embedding or topic.embedding_key != key:
            stale.append((topic, text, key))

    if not stale:
        return []

    vectors = embed_texts([text for _, text, _ in stale])
    for (topic, _, key), vector in zip(stale, vectors):
        topic.embedding = encode_vector(vector)
        topic.embedding_key = key
        topic.save(update_fields=['embedding', 'embedding_key'])
    return [topic for topic, _, _ in stale]


def rank_many(queries, topics, top_n=3, refresh=False):
    """여러 후보를 한 번에 비교한다. 반환은 후보별 순위 리스트.

    Topic 임베딩은 **한 번만** 갱신하고, 후보 임베딩도 **한 번의 호출로 묶는다.**
    후보마다 따로 돌리면 같은 Topic을 반복해서 인코딩하게 된다.
    """
    queries = list(queries)
    topics = list(topics)
    if not topics or not queries:
        return [[] for _ in queries]

    refresh_topic_embeddings(topics, refresh=refresh)
    decoded = [(t, decode_vector(t.embedding)) for t in topics]

    results = []
    for query_vector in embed_texts(queries):
        scored = [
            {'topic': topic, 'score': cosine_similarity(query_vector, vector)}
            for topic, vector in decoded
        ]
        scored.sort(key=lambda row: row['score'], reverse=True)
        results.append(scored[:top_n])
    return results


def rank_topics(query, topics, top_n=3, refresh=False):
    """query와 가장 가까운 Topic을 점수 내림차순으로 top_n개."""
    return rank_many([query], topics, top_n=top_n, refresh=refresh)[0]


# 참고 라벨 기준값. **판정이 아니라 읽는 힌트다.**
# 유사도 절대값만으로 자르지 않고 1위와 2위의 간격을 같이 본다 —
# 점수 하나만 보면 임계값으로 자르고 싶어지는데 이 판정은 그런 성격이 아니다.
WEAK_SCORE = 0.35
CLEAR_GAP = 0.10


def advice(ranked):
    """상위 후보에 붙일 참고 라벨. **결정하지 않는다.**"""
    if not ranked:
        return '비교 대상 없음'

    top = ranked[0]
    exposure = top['topic'].exposure_count
    gap = top['score'] - (ranked[1]['score'] if len(ranked) > 1 else 0.0)

    if exposure == 0:
        return '노출 0회 — 신규 소재'
    if top['score'] < WEAK_SCORE:
        return f'노출 {exposure}회 · 유사도 낮음 — 참고'
    if gap >= CLEAR_GAP:
        return f'노출 {exposure}회 · 1위 뚜렷 — 중복 검토'
    return f'노출 {exposure}회 · 1·2위 접전 — 사람 확인'
