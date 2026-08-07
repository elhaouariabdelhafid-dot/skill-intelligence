#!/usr/bin/env bash
# Déroule tout le cycle : création, sujet, ouverture, réponse, évaluation.
set -uo pipefail
BASE="${BASE:-http://localhost:8010}"
jq() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

echo "== Connexion formateur =="
FT=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"formateur@cmh.ma","password":"Formateur@2026"}' | jq "d['access_token']")
[ -z "$FT" ] && { echo "ÉCHEC"; exit 1; }
F=(-H "Authorization: Bearer $FT" -H "Content-Type: application/json")
echo "OK"

echo -e "\n== 1. Créer une session (participant : HAFID id=4) =="
SID=$(curl -s -X POST "$BASE/api/sessions" "${F[@]}" \
  -d '{"title":"Examen Cloud AWS — juillet","services":["IAM","VPC","S3"],"participants":[4]}' | jq "d['id']")
echo "Session #$SID"

echo -e "\n== 2. Générer le sujet =="
curl -s -X POST "$BASE/api/sessions/$SID/generate" "${F[@]}"; echo

echo -e "\n== 3. Ouvrir la session =="
curl -s -X POST "$BASE/api/sessions/$SID/open" "${F[@]}"; echo

echo -e "\n== 4. Exporter le PDF =="
curl -s -H "Authorization: Bearer $FT" "$BASE/api/sessions/$SID/pdf" -o /tmp/sujet.pdf
ls -lh /tmp/sujet.pdf | awk '{print "PDF généré :", $9, $5}'

echo -e "\n== 5. Connexion collaborateur =="
CT=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"hafid@cmh.ma","password":"Hafid@2026"}' | jq "d['access_token']")
C=(-H "Authorization: Bearer $CT" -H "Content-Type: application/json")

echo -e "\n== 6. Ses sessions ouvertes =="
curl -s "${C[@]}" "$BASE/api/sessions/me/open"; echo

echo -e "\n== 7. Répondre à la première question =="
QID=$(curl -s "${C[@]}" "$BASE/api/sessions/me/$SID/questions" | jq "d[0]['question_id']")
echo "Question : $QID"
curl -s -X POST "$BASE/api/sessions/me/answer" "${C[@]}" \
  -d "{\"session_id\":$SID,\"question_id\":\"$QID\",\"answer_text\":\"Un groupe de securite agit comme un pare-feu virtuel a etat qui controle le trafic entrant et sortant des instances EC2 dans un VPC.\"}"; echo

echo -e "\n== 8. Lancer l'évaluation (tâche de fond) =="
curl -s -X POST "$BASE/api/sessions/$SID/evaluate" "${F[@]}"; echo

echo -e "\n== 9. Suivre la progression (20 s) =="
for i in 1 2 3 4; do
  sleep 5
  curl -s "${F[@]}" "$BASE/api/sessions/$SID/status"; echo
done

echo -e "\nSuivez la fin avec :"
echo "  curl -s -H \"Authorization: Bearer \$FT\" $BASE/api/sessions/$SID/results"
