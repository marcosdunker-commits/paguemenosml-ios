#!/bin/bash
set -e

echo "=== Deploy PagueMenos ML ==="

# 1. Dependências do sistema
apt-get update -q
apt-get install -y -q python3-venv python3-pip nginx certbot python3-certbot-nginx

# 2. Ambiente Python
cd /root/PagueMenosML
python3 -m venv venv
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r backend/requirements.txt -q

echo "=== Python OK ==="

# 3. Serviço systemd (novo arquivo, não toca em nada existente)
cp /root/PagueMenosML/paguemenosml.service /etc/systemd/system/paguemenosml.service
systemctl daemon-reload
systemctl enable paguemenosml
systemctl restart paguemenosml
sleep 2
systemctl is-active paguemenosml && echo "=== Serviço rodando ===" || echo "ERRO no serviço"

# 4. Nginx — novo site (não altera configs existentes)
cp /root/PagueMenosML/nginx.conf /etc/nginx/sites-available/paguemenosml.shop
ln -sf /etc/nginx/sites-available/paguemenosml.shop /etc/nginx/sites-enabled/paguemenosml.shop
nginx -t && systemctl reload nginx

echo "=== Nginx OK ==="

# 5. SSL Let's Encrypt
certbot --nginx -d paguemenosml.shop -d www.paguemenosml.shop --non-interactive --agree-tos -m contatopaguemenosml@gmail.com

echo ""
echo "=== PRONTO! Site no ar em https://paguemenosml.shop ==="
