#!/usr/bin/env bash
set -uo pipefail
BASE="${BASE:-http://localhost:8010}"
tok() { curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$1\",\"password\":\"$2\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"; }

AT=$(tok admin@cmh.ma Admin@2026)
RT=$(tok rh@cmh.ma Rh@2026)
A=(-H "Authorization: Bearer $AT" -H "Content-Type: application/json")

echo "== 1. Paramètres actuels =="
curl -s "${A[@]}" "$BASE/api/admin/settings" | head -c 400; echo

echo -e "\n== 2. Modifier le seuil de maîtrise (60 -> 65) =="
curl -s -X PUT "$BASE/api/admin/settings" "${A[@]}" -d '{"key":"skill_threshold","value":"65"}'; echo

echo -e "\n== 3. Valeur refusée (seuil à 150) =="
curl -s -o /dev/null -w "HTTP %{http_code} (400 attendu)\n" \
  -X PUT "$BASE/api/admin/settings" "${A[@]}" -d '{"key":"skill_threshold","value":"150"}'

echo -e "\n== 4. Pondération incohérente -> avertissement =="
curl -s -X PUT "$BASE/api/admin/settings" "${A[@]}" -d '{"key":"weight_grader","value":"0.7"}'; echo

echo -e "\n== 5. État du corpus =="
curl -s "${A[@]}" "$BASE/api/admin/corpus"; echo

echo -e "\n== 6. Journal d'audit =="
curl -s "${A[@]}" "$BASE/api/admin/audit?limit=5" | head -c 400; echo

echo -e "\n== 7. Le RH ne peut pas modifier les paramètres =="
curl -s -o /dev/null -w "HTTP %{http_code} (403 attendu)\n" \
  -X PUT "$BASE/api/admin/settings" -H "Authorization: Bearer $RT" \
  -H "Content-Type: application/json" -d '{"key":"skill_threshold","value":"50"}'

echo -e "\n== 8. Réinitialisation =="
curl -s -X POST "$BASE/api/admin/settings/reset" "${A[@]}"; echo
echo -e "\nAdministration vérifiée."
