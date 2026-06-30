from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from bs4 import BeautifulSoup
import cloudscraper
import requests
import re
import os
import time
import smtplib
import threading
from email.mime.text import MIMEText
from urllib.parse import unquote, urlparse, parse_qs

def _load_env(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()
    except Exception:
        pass

_load_env(os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI()  # v2

MATT_TOOL = "18895981"
MATT_WORD = "paguemenos"


def afiliado(permalink: str) -> str:
    # Desempacota links de rastreamento do ML (click1.mercadolivre.com.br)
    if "click1.mercadolivre.com.br" in permalink:
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(permalink).query)
            real = qs.get("url", [None])[0]
            if real:
                permalink = unquote(real)
        except Exception:
            pass
    base = permalink.split("#")[0].split("?")[0]
    return f"{base}?matt_tool={MATT_TOOL}&matt_word={MATT_WORD}"


def gerar_links_meli(urls: list[str]) -> dict[str, str]:
    """Chama a API oficial do ML para gerar links meli.la em lote.
    Requer ML_COOKIE e ML_CSRF_TOKEN no ambiente.
    Retorna dict {url_original: meli_la_url}."""
    cookie = os.environ.get("ML_COOKIE", "")
    csrf = os.environ.get("ML_CSRF_TOKEN", "")
    if not cookie or not csrf:
        return {}
    try:
        r = requests.post(
            "https://www.mercadolivre.com.br/affiliate-program/api/v2/affiliates/createLink",
            json={"urls": urls, "tag": MATT_WORD},
            headers={
                "Content-Type": "application/json",
                "cookie": cookie,
                "x-csrf-token": csrf,
                "origin": "https://www.mercadolivre.com.br",
                "referer": "https://www.mercadolivre.com.br/afiliados/linkbuilder",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        result = {}
        items = data.get("urls", [])
        for i, item in enumerate(items):
            short = item.get("short_url", "")
            if i < len(urls) and short:
                result[urls[i]] = short
        return result
    except Exception:
        return {}


def aplicar_links_meli(items: list[dict]) -> list[dict]:
    """Tenta substituir os links por meli.la; fallback mantém o ?matt_tool."""
    clean_urls = [it["link"].split("?")[0] for it in items]
    meli_map = gerar_links_meli(clean_urls)
    if meli_map:
        for it in items:
            clean = it["link"].split("?")[0]
            it["link"] = meli_map.get(clean, it["link"])
    return items


def melhor_imagem(url: str) -> str:
    url = re.sub(r"-[A-Z]\.jpg$", "-O.jpg", url)
    return url.replace("http://", "https://")


def parse_preco(aria_label: str):
    if not aria_label:
        return None
    nums = re.findall(r"\d+", aria_label)
    if not nums:
        return None
    reais = int(nums[0])
    centavos = int(nums[1]) if len(nums) > 1 and "centavos" in aria_label else 0
    return reais + centavos / 100


def fmt_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


STOPWORDS = {'de','do','da','dos','das','e','com','para','em','a','o','os','as','um','uma','no','na','ao','ou','por'}

# Termos genéricos de categoria: peso baixo na pontuação (não são diferenciais de busca)
_TERMOS_GENERICOS = {
    'celular','smartphone','notebook','laptop','tablet','fone','headphone','monitor',
    'camera','câmera','impressora','roteador','teclado','mouse','projetor','smartwatch',
    'drone','webcam','pendrive','headset','televisao','televisão','caixa',
    'camisa','camiseta','blusa','vestido','calca','calça','bermuda','short',
    'jaqueta','casaco','regata','saia','tenis','tênis','sandalia','sandália',
    'chinelo','bota','sapato','roupa','calcado','calçado',
    'whey','vitamina','proteina','proteína','suplemento','bcaa','colágeno','colageno',
    'sofa','sofá','cama','colchao','colchão','panela','geladeira','aspirador',
    'ventilador','microondas','cafeteira','tapete','mesa','cadeira','produto','kit',
}

CATEGORIAS_KEYWORDS = {
    'MLB1051': ['tv','televisao','televisão','smart tv','celular','smartphone','iphone','samsung','notebook',
                'laptop','tablet','ipad','fone','headphone','airpod','monitor','câmera','camera','impressora',
                'roteador','wi-fi','wifi','carregador','teclado','mouse','ssd','kindle','alexa','projetor',
                'caixa de som','bluetooth','smartwatch','drone','webcam','pendrive','headset','gpu','gamer'],
    'MLB1430': ['camisa','camiseta','blusa','vestido','calça','calca','bermuda','short','jaqueta','moletom',
                'agasalho','casaco','polo','regata','saia','macacão','pijama','cueca','sutiã','meia','legging',
                'tenis','tênis','sandalia','sandália','chinelo','bota','sapato','nike','adidas','vans',
                'new balance','puma','asics','olympikus','roupa'],
    'MLB1276': ['whey','creatina','vitamina','proteina','proteína','suplemento','bcaa','glutamina',
                'colágeno','colageno','omega','pre-treino','aminoacido','termogenico','fitness'],
    'MLB1574': ['sofa','sofá','cama','colchao','colchão','panela','fogao','geladeira','liquidificador',
                'aspirador','ventilador','ar condicionado','microondas','cafeteira','tapete','cortina',
                'organizador','armario','rack','estante','mesa','cadeira','churrasqueira','air fryer',
                'frigideira','chaleira','purificador'],
    'MLB1132': ['tenis','tênis','sneaker','calcado','sapato','sandalia','chinelo','bota','nike','adidas'],
}


def _detectar_categoria(query: str) -> str:
    q = query.lower()
    for cat_id, keywords in CATEGORIAS_KEYWORDS.items():
        if any(k in q for k in keywords):
            return cat_id
    return ''


def _tokens(texto: str) -> set:
    palavras = re.sub(r'[^\w\s]', ' ', texto.lower()).split()
    return set(w for w in palavras if len(w) > 2 and w not in STOPWORDS)


def _match(query: str, nome: str) -> bool:
    tq = _tokens(query)
    tn = _tokens(nome)
    if not tq:
        return True
    return len(tq & tn) / len(tq) >= 0.5


def _scrape_pagina(scraper, url: str) -> list:
    try:
        r = scraper.get(url, timeout=30)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        for card in soup.select(".poly-card"):
            titulo_el = card.select_one(".poly-component__title")
            if not titulo_el:
                continue
            nome = titulo_el.get_text(strip=True)
            link = titulo_el.get("href", "")
            if not link:
                continue
            preco_de_el = card.select_one(".andes-money-amount--previous")
            preco_por_el = card.select_one(".andes-money-amount--cents-superscript")
            preco_de = parse_preco(preco_de_el.get("aria-label", "") if preco_de_el else "")
            preco_por = parse_preco(preco_por_el.get("aria-label", "") if preco_por_el else "")
            if not preco_por:
                continue
            desconto = (
                int(((preco_de - preco_por) / preco_de) * 100)
                if preco_de and preco_de > preco_por else 0
            )
            img_el = card.select_one("img")
            img_url = ""
            if img_el:
                for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
                    val = img_el.get(attr, "")
                    if val and val.startswith("http"):
                        img_url = melhor_imagem(val)
                        break
            rating = 0.0
            reviews = 0
            rating_el = card.select_one(".poly-reviews__rating")
            if rating_el:
                try:
                    rating = float(rating_el.get_text(strip=True).replace(",", "."))
                except Exception:
                    pass
            reviews_el = card.select_one(".poly-reviews__total")
            if reviews_el:
                txt = re.sub(r"[^\d]", "", reviews_el.get_text())
                reviews = int(txt) if txt else 0
            items.append({
                "nome": nome,
                "preco": preco_por,
                "preco_de": preco_de if preco_de and preco_de > preco_por else None,
                "desconto": desconto,
                "imagem": img_url,
                "link": afiliado(link),
                "rating": rating,
                "reviews": reviews,
            })
        return items
    except Exception:
        return []


def buscar_ml(query: str, limit: int = 16):
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    cat_id = _detectar_categoria(query)
    results = []
    seen = set()
    sem_novos = 0

    def _add(items):
        added = 0
        for it in items:
            key = it["link"].split("?")[0]
            if key not in seen and _match(query, it["nome"]):
                seen.add(key)
                results.append(it)
                added += 1
        return added

    for pagina in range(1, 101):
        if len(results) >= limit:
            break
        url = (
            f"https://www.mercadolivre.com.br/ofertas?page={pagina}&category={cat_id}"
            if cat_id
            else f"https://www.mercadolivre.com.br/ofertas?page={pagina}"
        )
        items = _scrape_pagina(scraper, url)
        if not items:
            sem_novos += 1
            if sem_novos >= 5:
                break
            continue
        novos = _add(items)
        sem_novos = 0 if novos else sem_novos + 1
        if sem_novos >= 10:
            break
        time.sleep(0.3)

    # Ordena: melhor correspondência primeiro; empate pelo maior desconto
    results.sort(key=lambda x: (-_score(query, x["nome"]), -(x["desconto"] or 0)))
    return results[:limit]


_ofertas_cache: dict = {"data": [], "ts": 0.0}
CACHE_TTL = 300  # 5 minutos


_CATEGORIAS_ROTACAO = ['', 'MLB1051', 'MLB1430', 'MLB1276', 'MLB1574', 'MLB1132']
_rotacao_idx = 0


def _atualizar_ofertas_background():
    global _rotacao_idx
    while True:
        try:
            cat = _CATEGORIAS_ROTACAO[_rotacao_idx % len(_CATEGORIAS_ROTACAO)]
            _rotacao_idx += 1
            data = buscar_ofertas_ml(14, categoria=cat)
            if data:
                data = aplicar_links_meli(data)
                _ofertas_cache["data"] = data
                _ofertas_cache["ts"] = time.time()
        except Exception:
            pass
        time.sleep(300)


threading.Thread(target=_atualizar_ofertas_background, daemon=True).start()


def buscar_ofertas_ml(limit: int = 14, categoria: str = ''):
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    if categoria:
        url = f"https://www.mercadolivre.com.br/ofertas?category={categoria}"
    else:
        url = "https://www.mercadolivre.com.br/ofertas"
    r = scraper.get(url, timeout=30)
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []

    for card in soup.select(".poly-card"):
        titulo_el = card.select_one(".poly-component__title")
        if not titulo_el:
            continue
        nome = titulo_el.get_text(strip=True)
        link = titulo_el.get("href", "")
        if not link:
            continue

        preco_de_el = card.select_one(".andes-money-amount--previous")
        preco_por_el = card.select_one(".andes-money-amount--cents-superscript")
        preco_de = parse_preco(preco_de_el.get("aria-label", "") if preco_de_el else "")
        preco_por = parse_preco(preco_por_el.get("aria-label", "") if preco_por_el else "")

        if not preco_por:
            continue

        desconto = (
            int(((preco_de - preco_por) / preco_de) * 100)
            if preco_de and preco_de > preco_por
            else 0
        )

        img_el = card.select_one("img")
        img_url = ""
        if img_el:
            for attr in ["src", "data-src", "data-lazy-src", "data-original"]:
                val = img_el.get(attr, "")
                if val and val.startswith("http"):
                    img_url = melhor_imagem(val)
                    break

        rating = 0.0
        reviews = 0
        rating_el = card.select_one(".poly-reviews__rating")
        if rating_el:
            try:
                rating = float(rating_el.get_text(strip=True).replace(",", "."))
            except Exception:
                pass
        reviews_el = card.select_one(".poly-reviews__total")
        if reviews_el:
            txt = re.sub(r"[^\d]", "", reviews_el.get_text())
            reviews = int(txt) if txt else 0

        results.append({
            "nome": nome,
            "preco": preco_por,
            "preco_de": preco_de if preco_de and preco_de > preco_por else None,
            "desconto": desconto,
            "imagem": img_url,
            "link": afiliado(link),
            "rating": rating,
            "reviews": reviews,
        })

        if len(results) >= limit:
            break

    return results


MOCK_DATA = [
    {"nome": "Apple iPhone 15 128GB Preto Oficial Lacrado", "preco": 3299.0, "preco_de": 4999.0, "desconto": 34, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.8, "reviews": 12400},
    {"nome": "Apple iPhone 15 Pro 256GB Titânio Natural", "preco": 5999.0, "preco_de": 7499.0, "desconto": 20, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.9, "reviews": 3200},
    {"nome": "Samsung Galaxy S24 128GB Preto Snapdragon", "preco": 2799.0, "preco_de": 3999.0, "desconto": 30, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.7, "reviews": 8900},
    {"nome": "Notebook Samsung Book Intel Core i5 8GB 256GB SSD", "preco": 2199.0, "preco_de": 2999.0, "desconto": 27, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.6, "reviews": 5400},
    {"nome": "Smart TV Samsung 50 4K UHD QLED 2024", "preco": 1799.0, "preco_de": 2799.0, "desconto": 36, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.8, "reviews": 7100},
    {"nome": "Fone Bluetooth JBL Tune 520BT Preto 57h Bateria", "preco": 199.0, "preco_de": 349.0, "desconto": 43, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.5, "reviews": 21000},
    {"nome": "Air Fryer Philips Walita 4.1L Digital Preta", "preco": 349.0, "preco_de": 599.0, "desconto": 42, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.9, "reviews": 34000},
    {"nome": "Tênis Nike Revolution 6 Next Nature Masculino", "preco": 219.0, "preco_de": 399.0, "desconto": 45, "imagem": "https://http2.mlstatic.com/D_NQ_NP_611642-MLA71783876451_092023-O.jpg", "link": "#", "rating": 4.7, "reviews": 9800},
]


class ContatoPayload(BaseModel):
    nome: str
    email: str
    mensagem: str


@app.post("/api/contato")
def contato(payload: ContatoPayload):
    smtp_user = os.environ.get("EMAIL_USER", "")
    smtp_pass = os.environ.get("EMAIL_PASS", "")
    destino = "contatopaguemenosml@gmail.com"

    if not smtp_user or not smtp_pass:
        return JSONResponse(status_code=503, content={"erro": "Email não configurado no servidor."})

    corpo = f"Nome: {payload.nome}\nEmail: {payload.email}\n\n{payload.mensagem}"
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = f"[PagueMenos ML] Mensagem de {payload.nome}"
    msg["From"] = smtp_user
    msg["To"] = destino
    msg["Reply-To"] = payload.email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, destino, msg.as_string())
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": str(e)})


@app.get("/api/ofertas")
def ofertas(limit: int = 14):
    global _ofertas_cache
    if time.time() - _ofertas_cache["ts"] < CACHE_TTL and _ofertas_cache["data"]:
        return {"resultados": _ofertas_cache["data"]}
    try:
        data = buscar_ofertas_ml(limit)
        if not data:
            data = MOCK_DATA[:limit]
        data = aplicar_links_meli(data)
        _ofertas_cache = {"data": data, "ts": time.time()}
    except Exception:
        data = MOCK_DATA[:limit]
    return {"resultados": data}


def _peso(tok: str) -> float:
    """Termos genéricos de categoria valem menos; marcas e modelos valem mais."""
    return 1.0 if tok in _TERMOS_GENERICOS else 2.5


def _score(query: str, nome: str) -> float:
    tq = _tokens(query)
    tn = _tokens(nome)
    if not tq:
        return 0.0
    total_w = sum(_peso(t) for t in tq)
    matched_w = sum(_peso(t) for t in tq if t in tn)
    if not matched_w:
        return 0.0
    ratio = matched_w / total_w
    missing = sum(1 for t in tq if t not in tn)
    ratio *= (0.2 ** missing)
    bonus = 1.5 if any(nome.lower().startswith(w) for w in tq) else 1.0
    return ratio * bonus


@app.get("/api/redirecionar")
def redirecionar(q: str = Query(..., min_length=1)):
    from fastapi.responses import RedirectResponse
    try:
        q_slug = q.strip().lower().replace(' ', '-')
        search_url = f"https://lista.mercadolivre.com.br/{q_slug}"
        meli = gerar_links_meli([search_url])
        link = meli.get(search_url, afiliado(search_url))
        return RedirectResponse(url=link, status_code=302)
    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": str(e)})


@app.get("/api/buscar")
def buscar(q: str = Query(..., min_length=1), limit: int = 16):
    try:
        results = buscar_ml(q.strip(), limit)
        if not results:
            results = MOCK_DATA[:limit]
        results = aplicar_links_meli(results)
        return {"resultados": results, "total": len(results), "query": q}
    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": str(e)})


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
