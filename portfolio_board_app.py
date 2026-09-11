# -*- coding: utf-8 -*-
"""
SCALE Research Portfolio — public board.

A standalone Streamlit app (separate from the private admin app.py) that shows
all ACTIVE projects grouped into the four research buckets, with the people on
each, and lets anyone reassign a project's bucket / edit its people, stage, and
name. Reads and writes data/projects.json in scale-nssa/project-database, so it
stays in sync with the main database.

Deploy as its own Streamlit Community Cloud app (main file: portfolio_board_app.py)
and set Sharing → Public. Requires the same secrets as app.py: GITHUB_TOKEN, REPO_NAME.
"""
import json
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="SCALE Research Portfolio", page_icon="📋", layout="wide")

# ── Constants (kept consistent with app.py) ──────────────────────────────────
BUCKETS = ["Frontier Model Studies", "Measures & Benchmarks",
           "Tutoring & AI Causal", "Implementation & Other"]
BUCKET_COLOR = {
    "Frontier Model Studies":   "#5a5fc0",
    "Measures & Benchmarks":    "#0d8a99",
    "Tutoring & AI Causal":     "#b3364d",
    "Implementation & Other":   "#bd7a2c",
}
STAGE_LABELS = {
    "potential": "Potential", "brainstorm": "Brainstorm", "pre_impl": "Pre-implementation",
    "implementation": "Implementation", "data_wait": "Waiting for data", "analysis": "Analysis",
    "writing": "Writing", "complete": "Complete", "sunsetted": "Sunsetted",
    "holding": "Holding", "to_update": "To Update",
}
STAGES = list(STAGE_LABELS.keys())
EDITABLE_STAGES = [s for s in STAGES if s not in ("complete", "sunsetted")]
TEAM_ROLES = ["Lead", "Support", "Advisor", "Collaborator"]
ROLE_RANK = {"Lead": 0, "Collaborator": 1, "Support": 2, "Advisor": 3}
EXCLUDE = {"complete", "sunsetted"}
REPO_DEFAULT = "scale-nssa/project-database"
DATA_PATH = "data/projects.json"

# ── Data I/O (GitHub-backed, with local fallback) ────────────────────────────
def _repo():
    from github import Github
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        return None
    return Github(token).get_repo(st.secrets.get("REPO_NAME", REPO_DEFAULT))

@st.cache_data(ttl=30)
def load_projects():
    repo = _repo()
    if repo:
        f = repo.get_contents(DATA_PATH)
        return json.loads(f.decoded_content)
    return json.loads((Path(__file__).parent / DATA_PATH).read_text(encoding="utf-8"))

@st.cache_data(ttl=300)
def load_roster():
    """Active team-member names for the add-person picker."""
    try:
        repo = _repo()
        if repo:
            team = json.loads(repo.get_contents("data/team_members.json").decoded_content)
        else:
            team = json.loads((Path(__file__).parent / "data/team_members.json").read_text(encoding="utf-8"))
        return sorted([m["name"] for m in team if m.get("status") == "Active"])
    except Exception:
        return []

def apply_and_save(pid, mutate, summary, editor):
    """Fetch fresh, mutate the one project (or append when pid is None), commit."""
    repo = _repo()
    who = (editor or "someone").strip() or "someone"
    if repo:
        f = repo.get_contents(DATA_PATH)
        projects = json.loads(f.decoded_content)
        if pid is None:
            projects.append(mutate(None))
        else:
            for p in projects:
                if p["id"] == pid:
                    mutate(p); break
        content = json.dumps(projects, indent=2, ensure_ascii=False)
        repo.update_file(DATA_PATH, f"Portfolio board: {summary} — via public board by {who}",
                         content, f.sha)
    else:
        path = Path(__file__).parent / DATA_PATH
        projects = json.loads(path.read_text(encoding="utf-8"))
        if pid is None:
            projects.append(mutate(None))
        else:
            for p in projects:
                if p["id"] == pid:
                    mutate(p); break
        path.write_text(json.dumps(projects, indent=2, ensure_ascii=False), encoding="utf-8")
    st.cache_data.clear()

# ── Helpers ──────────────────────────────────────────────────────────────────
def dedupe_team(team):
    seen = {}
    for m in (team or []):
        nm = m.get("name")
        if not nm:
            continue
        if nm not in seen or ROLE_RANK.get(m.get("role"), 9) < ROLE_RANK.get(seen[nm], 9):
            seen[nm] = m.get("role") or ""
    return [{"name": n, "role": r} for n, r in
            sorted(seen.items(), key=lambda kv: (ROLE_RANK.get(kv[1], 9), kv[0]))]

def bucket_of(p):
    b = (p.get("overview") or {}).get("research_bucket")
    return b if b in BUCKETS else "Implementation & Other"

def active_projects(projects):
    return [p for p in projects if (p.get("process") or {}).get("stage") not in EXCLUDE]

# ── Session ──────────────────────────────────────────────────────────────────
if "editor" not in st.session_state:
    st.session_state.editor = ""

# ── Header ───────────────────────────────────────────────────────────────────
projects = load_projects()
roster = load_roster()
active = active_projects(projects)
people = sorted({m["name"] for p in active for m in (dedupe_team((p.get("overview") or {}).get("team")))})
roster_all = sorted(set(roster) | set(people))

st.title("📋 SCALE Active Research Portfolio")
c1, c2 = st.columns([3, 1])
with c1:
    st.caption(f"{len(active)} active projects · {len(people)} people · grouped into 4 research buckets. "
               "Excludes Done & Sunsetted. Live from the project database — **anyone can edit**.")
with c2:
    st.session_state.editor = st.text_input("Your name (for edit history)", value=st.session_state.editor,
                                             placeholder="optional")

edit_mode = st.toggle("✏️ Edit mode", value=False,
                      help="Turn on to move projects between buckets and edit people, stage, or name.")

person_filter = st.multiselect("Highlight people", people, placeholder="Show everyone",
                               help="Dim projects that don't include the selected people.")

# ── Add project ──────────────────────────────────────────────────────────────
if edit_mode:
    with st.expander("➕ Add a project"):
        with st.form("add_project"):
            a1, a2, a3 = st.columns([3, 2, 2])
            np_name = a1.text_input("Project name *")
            np_bucket = a2.selectbox("Bucket", BUCKETS)
            np_stage = a3.selectbox("Stage", EDITABLE_STAGES,
                                    format_func=lambda s: STAGE_LABELS[s])
            if st.form_submit_button("Add project", type="primary") and np_name.strip():
                import re
                base = re.sub(r"[^A-Za-z0-9]+", "_", np_name.strip()).strip("_") or "project"
                existing = {p["id"] for p in projects}
                nid, i = base, 2
                while nid in existing:
                    nid = f"{base}_{i}"; i += 1
                def _new(_):
                    return {"id": nid, "overview": {"name": np_name.strip(), "team": [],
                            "research_bucket": np_bucket, "partners": [], "domain": [], "research_type": []},
                            "process": {"stage": np_stage, "todo": []},
                            "study_info": {}, "for_reports": {}, "funding": {}, "metadata": {}}
                apply_and_save(None, _new, f"add project {np_name.strip()}", st.session_state.editor)
                st.success(f"Added “{np_name.strip()}”.")
                st.rerun()

# ── Board ────────────────────────────────────────────────────────────────────
cols = st.columns(4)
for col, bucket in zip(cols, BUCKETS):
    items = sorted([p for p in active if bucket_of(p) == bucket],
                   key=lambda p: ((p.get("overview") or {}).get("name") or p["id"]).lower())
    color = BUCKET_COLOR[bucket]
    with col:
        st.markdown(
            f"<div style='border-bottom:3px solid {color};padding-bottom:6px;margin-bottom:10px'>"
            f"<span style='font-weight:700'>{bucket}</span> "
            f"<span style='color:{color};font-family:monospace;float:right'>{len(items)}</span></div>",
            unsafe_allow_html=True)
        for p in items:
            ov = p.get("overview") or {}
            pid = p["id"]
            name = ov.get("name") or pid
            stage = (p.get("process") or {}).get("stage")
            team = dedupe_team(ov.get("team"))
            names = [m["name"] for m in team]
            dim = bool(person_filter) and not any(n in person_filter for n in names)
            opacity = "0.35" if dim else "1"

            leads = ", ".join(f"<b>{m['name']}</b>" if m["role"] == "Lead" else m["name"] for m in team) or "<i>No one assigned</i>"
            st.markdown(
                f"<div style='opacity:{opacity};border:1px solid #ddd;border-left:3px solid {color};"
                f"border-radius:10px;padding:9px 11px;margin-bottom:9px'>"
                f"<div style='font-weight:600;font-size:0.95rem'>{name}</div>"
                f"<div style='font-family:monospace;font-size:0.72rem;color:{color};margin:3px 0 5px'>{STAGE_LABELS.get(stage, stage)}</div>"
                f"<div style='font-size:0.82rem;color:#555'>{leads}</div></div>",
                unsafe_allow_html=True)

            if edit_mode:
                with st.expander("✏️ Edit"):
                    new_name = st.text_input("Name", value=name, key=f"nm_{pid}")
                    e1, e2 = st.columns(2)
                    new_bucket = e1.selectbox("Bucket", BUCKETS, index=BUCKETS.index(bucket), key=f"bk_{pid}")
                    _si = STAGES.index(stage) if stage in STAGES else 0
                    new_stage = e2.selectbox("Stage", STAGES, index=_si,
                                             format_func=lambda s: STAGE_LABELS[s], key=f"stg_{pid}")

                    st.markdown("**Team**")
                    new_team = []
                    for i, m in enumerate(team):
                        t1, t2, t3 = st.columns([3, 3, 1])
                        t1.markdown(f"<div style='padding-top:6px'>{m['name']}</div>", unsafe_allow_html=True)
                        role = t2.selectbox("role", TEAM_ROLES,
                                            index=TEAM_ROLES.index(m["role"]) if m["role"] in TEAM_ROLES else 1,
                                            key=f"rl_{pid}_{i}", label_visibility="collapsed")
                        keep = not t3.checkbox("✕", key=f"del_{pid}_{i}", help="Remove")
                        if keep:
                            new_team.append({"name": m["name"], "role": role})

                    ax1, ax2 = st.columns([3, 3])
                    add_opts = [""] + [n for n in roster_all if n not in names]
                    add_name = ax1.selectbox("Add person", add_opts, key=f"add_{pid}",
                                             label_visibility="collapsed")
                    add_role = ax2.selectbox("role", TEAM_ROLES, index=1, key=f"addrole_{pid}",
                                             label_visibility="collapsed")
                    if add_name:
                        new_team.append({"name": add_name, "role": add_role})

                    b1, b2 = st.columns([1, 1])
                    if b1.button("💾 Save", type="primary", key=f"save_{pid}", use_container_width=True):
                        nn, nb, ns, nt = new_name.strip() or name, new_bucket, new_stage, new_team
                        def _mut(pr):
                            pr.setdefault("overview", {})
                            pr["overview"]["name"] = nn
                            pr["overview"]["research_bucket"] = nb
                            pr["overview"]["team"] = nt
                            pr.setdefault("process", {})["stage"] = ns
                        apply_and_save(pid, _mut, f"edit {nn}", st.session_state.editor)
                        st.success("Saved.")
                        st.rerun()
                    if b2.button("🗑 Remove", key=f"rm_{pid}", use_container_width=True):
                        st.session_state[f"confirm_rm_{pid}"] = True
                    if st.session_state.get(f"confirm_rm_{pid}"):
                        st.warning("Remove this project from the database?")
                        if st.button("Yes, remove", key=f"yesrm_{pid}"):
                            def _rm(_):  # noqa
                                return None
                            # remove by rebuilding without this id
                            repo = _repo()
                            who = st.session_state.editor or "someone"
                            if repo:
                                f = repo.get_contents(DATA_PATH)
                                allp = [x for x in json.loads(f.decoded_content) if x["id"] != pid]
                                repo.update_file(DATA_PATH, f"Portfolio board: remove {name} — via public board by {who}",
                                                 json.dumps(allp, indent=2, ensure_ascii=False), f.sha)
                            else:
                                path = Path(__file__).parent / DATA_PATH
                                allp = [x for x in json.loads(path.read_text(encoding="utf-8")) if x["id"] != pid]
                                path.write_text(json.dumps(allp, indent=2, ensure_ascii=False), encoding="utf-8")
                            st.cache_data.clear()
                            st.session_state.pop(f"confirm_rm_{pid}", None)
                            st.rerun()

st.divider()
st.caption("Leads are **bold**. Changes write to data/projects.json in scale-nssa/project-database. "
           "This is a public, editable view — the private admin app has the full editing tools.")
