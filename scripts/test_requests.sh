#!/usr/bin/env bash
# Déroule le circuit manager -> RH -> formateur.
set -uo pipefail
BASE="${BASE:-http://localhost:8010}"
tok() { curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$1\",\"password\":\"$2\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"; }

MT=$(tok manager@cmh.ma Manager@2026)
HT=$(tok rh@cmh.ma Rh@2026)
FT=$(tok formateur@cmh.ma Formateur@2026)
[ -z "$MT" ] && { echo "ÉCHEC connexion"; exit 1; }
M=(-H "Authorization: Bearer $MT" -H "Content-Type: application/json")
H=(-H "Authorization: Bearer $HT" -H "Content-Type: application/json")
F=(-H "Authorization: Bearer $FT" -H "Content-Type: application/json")

echo "== 1. MANAGER — soumettre une demande =="
RID=$(curl -s -X POST "$BASE/api/requests" "${M[@]}" -d '{
  "title":"Renforcement IAM et VPC — équipe Cloud",
  "justification":"Deux collaborateurs sont sous le seuil sur IAM et VPC, qui conditionnent Well-Architected.",
  "services":["IAM","VPC"],"participants":[4,5],"priority":"haute"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "Demande #$RID créée"

echo -e "\n== 2. MANAGER — suivre ses demandes =="
curl -s "${M[@]}" "$BASE/api/requests/mine" | head -c 300; echo

echo -e "\n== 3. RH — voir la file d'attente =="
curl -s "${H[@]}" "$BASE/api/requests?status=en_attente" | head -c 300; echo

echo -e "\n== 4. RH — valider la demande =="
curl -s -X POST "$BASE/api/requests/$RID/review" "${H[@]}" \
  -d '{"decision":"validée","comment":"Priorité confirmée, à planifier ce mois-ci."}' | head -c 300; echo

echo -e "\n== 5. FORMATEUR — voir les demandes validées =="
curl -s "${F[@]}" "$BASE/api/requests" | head -c 300; echo

echo -e "\n== 6. FORMATEUR — planifier (crée la session) =="
curl -s -X POST "$BASE/api/requests/$RID/plan" "${F[@]}" | head -c 350; echo

echo -e "\n== 7. Contrôle des rôles (formateur ne peut pas valider) =="
curl -s -o /dev/null -w "HTTP %{http_code} (403 attendu)\n" \
  -X POST "$BASE/api/requests/$RID/review" "${F[@]}" -d '{"decision":"validée"}'

echo -e "\n== 8. Synthèse =="
curl -s "${H[@]}" "$BASE/api/requests/summary"; echo
echo -e "\nCircuit vérifié."
