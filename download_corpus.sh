#!/usr/bin/env bash
# Télécharge le corpus AWS depuis les PDF officiels (les dépôts awsdocs sont vides)
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
[[ -d data/raw ]] || { echo "Lance ce script depuis ~/skill-intelligence"; exit 1; }

cd data/raw
rm -rf amazon-* iam-user-guide
mkdir -p whitepapers && cd whitepapers

URLS=(
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/framework/wellarchitected-framework.pdf"
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/security-pillar/wellarchitected-security-pillar.pdf"
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/reliability-pillar/wellarchitected-reliability-pillar.pdf"
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/cost-optimization-pillar/wellarchitected-cost-optimization-pillar.pdf"
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/performance-efficiency-pillar/wellarchitected-performance-efficiency-pillar.pdf"
"https://docs.aws.amazon.com/pdfs/wellarchitected/latest/operational-excellence-pillar/wellarchitected-operational-excellence-pillar.pdf"
"https://docs.aws.amazon.com/pdfs/vpc/latest/userguide/vpc-ug.pdf"
"https://docs.aws.amazon.com/pdfs/IAM/latest/UserGuide/iam-ug.pdf"
"https://docs.aws.amazon.com/pdfs/AmazonS3/latest/userguide/s3-userguide.pdf"
"https://docs.aws.amazon.com/pdfs/lambda/latest/dg/lambda-dg.pdf"
"https://docs.aws.amazon.com/pdfs/AWSEC2/latest/UserGuide/ec2-ug.pdf"
"https://docs.aws.amazon.com/pdfs/AmazonRDS/latest/UserGuide/rds-ug.pdf"
)

ok=0; fail=0
for url in "${URLS[@]}"; do
  name=$(basename "$url")
  if [[ -f "$name" ]]; then echo "SKIP $name (déjà là)"; ((ok++)); continue; fi
  if wget -q --timeout=60 --tries=2 "$url"; then
    echo "OK   $name  ($(du -h "$name" | cut -f1))"; ((ok++))
  else
    echo "FAIL $name"; ((fail++))
  fi
done

echo ""
echo "Téléchargés : $ok   Échecs : $fail"
echo "Volume total : $(du -sh . | cut -f1)"
[[ $ok -ge 4 ]] && echo "Corpus suffisant pour démarrer." || echo "ATTENTION : corpus trop petit."
