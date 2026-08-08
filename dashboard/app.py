"""Dashboard Streamlit — Skill Intelligence Platform.

Trois vues : Vue d'ensemble (RH), Profil individuel, Détail des réponses.
Connecté à PostgreSQL, affiche les vraies évaluations.

Lancement :
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from db.models import User, Submission, Evaluation, get_session
from skills.profile import compute_profile
from skills.recommendations import build_learning_plan

st.set_page_config(page_title="Skill Intelligence", page_icon="📊",
                   layout="wide")


@st.cache_data(ttl=30)
def load_users():
    s = get_session()
    users = [(u.id, u.name, u.role) for u in s.query(User).order_by(User.id).all()]
    s.close()
    return users


@st.cache_data(ttl=30)
def load_profile(uid: int):
    return compute_profile(uid)


@st.cache_data(ttl=30)
def load_plan(uid: int):
    return build_learning_plan(compute_profile(uid))


@st.cache_data(ttl=30)
def load_submissions(uid: int):
    s = get_session()
    rows = (s.query(Submission, Evaluation)
            .join(Evaluation, Evaluation.submission_id == Submission.id)
            .filter(Submission.user_id == uid).all())
    data = [{
        "service": sub.service, "skill": sub.skill,
        "difficulty": sub.difficulty, "bloom": sub.bloom_level,
        "answer": sub.answer_text,
        "grader": ev.grader_score, "reasoner": ev.reasoner_score,
        "critic": ev.critic_score, "final": ev.final_score,
        "feedback": ev.feedback, "details": ev.details,
    } for sub, ev in rows]
    s.close()
    return data


def level_label(score: float) -> str:
    if score >= 75: return "Avancé"
    if score >= 60: return "Confirmé"
    if score >= 40: return "Intermédiaire"
    return "Débutant"


# ============================================================ SIDEBAR
st.sidebar.title("📊 Skill Intelligence")
st.sidebar.caption("Évaluation des compétences Cloud AWS")

view = st.sidebar.radio("Vue", ["Vue d'ensemble", "Profil individuel",
                                "Détail des réponses"])

users = load_users()
if not users:
    st.warning("Aucun collaborateur en base. Importe des réponses d'abord.")
    st.stop()

# ============================================================ VUE 1 — RH
if view == "Vue d'ensemble":
    st.title("Vue d'ensemble — Équipe")
    st.caption("Cartographie des compétences de tous les collaborateurs")

    rows = []
    for uid, name, role in users:
        p = load_profile(uid)
        rows.append({"Collaborateur": name, "Niveau global": p["overall"],
                     "Évaluations": p["n_evaluations"],
                     "Niveau": level_label(p["overall"])})
    df = pd.DataFrame(rows).sort_values("Niveau global", ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Collaborateurs", len(df))
    c2.metric("Niveau moyen", f"{df['Niveau global'].mean():.1f}%")
    c3.metric("Évaluations totales", int(df["Évaluations"].sum()))

    st.subheader("Classement")
    st.dataframe(df, width="stretch", hide_index=True)
    st.bar_chart(df.set_index("Collaborateur")["Niveau global"])

    # Matrice compétences × collaborateurs
    st.subheader("Matrice des compétences par service")
    matrix = {}
    for uid, name, role in users:
        p = load_profile(uid)
        matrix[name] = p["services"]
    mdf = pd.DataFrame(matrix).T
    if not mdf.empty:
        st.dataframe(mdf.style.format("{:.0f}%").background_gradient(
            cmap="RdYlGn", vmin=0, vmax=100), width="stretch")

# ============================================================ VUE 2 — PROFIL
elif view == "Profil individuel":
    st.title("Profil de compétences")
    names = {f"{name} (id={uid})": uid for uid, name, role in users}
    choice = st.selectbox("Collaborateur", list(names.keys()))
    uid = names[choice]

    p = load_profile(uid)
    plan = load_plan(uid)

    c1, c2, c3 = st.columns(3)
    c1.metric("Niveau global", f"{p['overall']}%", level_label(p["overall"]))
    c2.metric("Évaluations", p["n_evaluations"])
    c3.metric("À renforcer", plan["n_gaps"])

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Niveau par service")
        svc_df = pd.DataFrame(
            [{"Service": k, "Niveau": v} for k, v in p["services"].items()]
        ).sort_values("Niveau")
        st.bar_chart(svc_df.set_index("Service")["Niveau"])

    with col_right:
        st.subheader("Plan de formation")
        if plan["n_gaps"] == 0:
            st.success("Profil solide — aucune formation critique nécessaire.")
        else:
            for rec in plan["recommendations"]:
                with st.expander(
                    f"🎯 {rec['service']} — {rec['current_level']}% "
                    f"(priorité {rec['priority']})"):
                    st.write("**À réviser :**")
                    for r in rec["resources"]:
                        st.markdown(f"- `{r['source']}`")
                        st.caption(r["excerpt"][:150] + "...")

# ============================================================ VUE 3 — DÉTAIL
else:
    st.title("Détail des réponses et évaluations")
    names = {f"{name} (id={uid})": uid for uid, name, role in users}
    choice = st.selectbox("Collaborateur", list(names.keys()))
    uid = names[choice]

    subs = load_submissions(uid)
    st.caption(f"{len(subs)} réponses évaluées")

    for i, s in enumerate(subs, 1):
        with st.expander(
            f"{i}. {s['service']} — score {s['final']}/4 "
            f"({s['difficulty']})"):
            st.write(f"**Réponse :** {s['answer'][:400]}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Exactitude", f"{s['grader']}/4")
            c2.metric("Raisonnement", f"{s['reasoner']}/4")
            c3.metric("Problèmes", f"{s['critic']}/4")
            st.info(s["feedback"])
            details = s.get("details") or {}
            if details.get("weaknesses"):
                st.write("**Points à améliorer :**")
                for w in details["weaknesses"]:
                    st.markdown(f"- {w[:200]}")

st.sidebar.divider()
st.sidebar.caption("PFA CMH · RAG + Agents LLM · Cloud AWS")
