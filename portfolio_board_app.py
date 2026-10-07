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
from urllib.parse import quote
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
# People allowed to make edits (everyone else is view-only)
EDITORS = ["Ana", "Carly", "Chris", "Lily", "Monica", "Paul", "Susanna"]
ROLE_RANK = {"Lead": 0, "Collaborator": 1, "Support": 2, "Advisor": 3}
EXCLUDE = {"complete", "sunsetted"}
REPO_DEFAULT = "scale-nssa/project-database"
DATA_PATH = "data/projects.json"
TEAM_PATH = "data/team_structure.json"

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
def load_statuses():
    """name -> roster status ("Active", "Collaborator", "Inactive", …) from team_members.json."""
    try:
        repo = _repo()
        if repo:
            team = json.loads(repo.get_contents("data/team_members.json").decoded_content)
        else:
            team = json.loads((Path(__file__).parent / "data/team_members.json").read_text(encoding="utf-8"))
        return {m["name"]: m.get("status") for m in team if m.get("name")}
    except Exception:
        return {}

def load_roster():
    """Active team members and collaborators, for the add-person picker."""
    return sorted(n for n, s in load_statuses().items() if s in SHOWN_STATUSES)

@st.cache_data(ttl=300)
def load_team_structure():
    """Vertical teams, primaries and workstreams for the Team structure view."""
    repo = _repo()
    if repo:
        return json.loads(repo.get_contents(TEAM_PATH).decoded_content)
    return json.loads((Path(__file__).parent / TEAM_PATH).read_text(encoding="utf-8"))

def apply_and_save(pid, mutate, summary, editor):
    """Fetch fresh, mutate the one project (or append when pid is None), commit."""
    if editor not in EDITORS:
        st.error("You don't have edit permission — select your name (research leads only).")
        return
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

# Who appears on the board: Active members and Collaborators (anyone on the team chart counts as Active).
# Inactive people and names missing from the roster are hidden from displays but kept in the data.
SHOWN_STATUSES = ("Active", "Collaborator")

def _chart_names():
    try:
        ts = load_team_structure()
    except Exception:
        return set()
    return ({l["name"] for l in ts.get("leaders", [])} | {t["lead"] for t in ts.get("teams", [])}
            | {n for t in ts.get("teams", []) for n, _ in t.get("members", [])})

def status_of(name):
    return "Active" if name in CHART_NAMES else STATUSES.get(name)

def is_shown(name):
    return status_of(name) in SHOWN_STATUSES

def is_collaborator(name):
    return status_of(name) == "Collaborator"

def visible_team(team):
    return [m for m in team if is_shown(m["name"])]

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
STATUSES = load_statuses()
CHART_NAMES = _chart_names()
roster = load_roster()
active = active_projects(projects)
people = sorted({m["name"] for p in active for m in visible_team(dedupe_team((p.get("overview") or {}).get("team")))})
team_people = [n for n in people if not is_collaborator(n)]   # collaborators stay off the "working together" map
roster_all = sorted(set(roster) | set(people))

st.title("📋 SCALE Active Research Portfolio")
# Views are linkable: ?view=portfolio|team|rubric, plus ?person=… or ?ws=… to focus on someone/a workstream
VIEWS = {"team": "👥 Team structure", "portfolio": "📋 Portfolio", "rubric": "🧭 Prioritization rubric"}
qp = st.query_params
_slugs = list(VIEWS)
# Style the view picker as large tabs that stay pinned at the top while scrolling
st.markdown("""<style>
.st-key-view_tabs { position: sticky; top: 3.75rem; z-index: 999; padding: 8px 0 10px;
                    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
                    border-bottom: 1px solid rgba(127,127,127,.25); }
.st-key-view_tabs div[role="radiogroup"] { gap: 10px; flex-wrap: wrap; }
.st-key-view_tabs [data-testid="stRadioOption"] {
    margin: 0 !important; padding: 10px 22px !important; border-radius: 10px; cursor: pointer;
    border: 1.5px solid #c9cdea; background: #eef0fb;
    transition: background .12s, border-color .12s; }
/* hide the radio circle, keep the text */
.st-key-view_tabs [data-testid="stRadioOption"] > div > div:not([data-testid="stMarkdownContainer"]) { display: none !important; }
.st-key-view_tabs [data-testid="stRadioOption"] p { font-size: 1.05rem; font-weight: 600; margin: 0; color: #2b2f6b !important; }
.st-key-view_tabs [data-testid="stRadioOption"]:hover { border-color: #5a5fc0; }
.st-key-view_tabs [data-testid="stRadioOption"][data-selected="true"],
.st-key-view_tabs [data-testid="stRadioOption"]:has(input:checked) {
    background: #5a5fc0; border-color: #5a5fc0; box-shadow: 0 2px 8px rgba(90,95,192,.35); }
.st-key-view_tabs [data-testid="stRadioOption"][data-selected="true"] p,
.st-key-view_tabs [data-testid="stRadioOption"]:has(input:checked) p { color: #fff !important; }
</style>""", unsafe_allow_html=True)
view = st.radio("View", list(VIEWS.values()), horizontal=True, label_visibility="collapsed", key="view_tabs",
                index=_slugs.index(qp.get("view")) if qp.get("view") in VIEWS else 0)
view_slug = _slugs[list(VIEWS.values()).index(view)]
if qp.get("view") != view_slug:   # switched tabs: drop the old focus, keep the URL shareable
    qp.clear()
    qp["view"] = view_slug
focus_person, focus_ws = qp.get("person"), qp.get("ws")

team_data = load_team_structure()
WORKSTREAMS = [w["name"] for w in team_data.get("workstreams", [])]
WS_COLOR = {w["name"]: w.get("color", "#94a3b8") for w in team_data.get("workstreams", [])}

# ── Team structure view ──────────────────────────────────────────────────────
def render_team_structure():
    import streamlit.components.v1 as components
    data = dict(team_data)
    by_person = {}
    for p in active:
        ov = p.get("overview") or {}
        stage = (p.get("process") or {}).get("stage")
        for m in visible_team(dedupe_team(ov.get("team"))):
            by_person.setdefault(m["name"], []).append({
                "name": ov.get("name") or p["id"], "role": m["role"], "workstream": ov.get("workstream"),
                "bucket": bucket_of(p), "stage": STAGE_LABELS.get(stage, stage)})
    data["projects"] = {n: sorted(v, key=lambda x: x["name"].lower()) for n, v in by_person.items()}
    data["all_projects"] = sorted(
        [{"name": (p.get("overview") or {}).get("name") or p["id"],
          "workstream": (p.get("overview") or {}).get("workstream"),
          "team": visible_team(dedupe_team((p.get("overview") or {}).get("team")))} for p in active],
        key=lambda x: x["name"].lower())
    data["bucket_colors"] = BUCKET_COLOR
    data["focus"] = {"person": focus_person, "ws": focus_ws}
    html = (Path(__file__).parent / "team_chart.html").read_text(encoding="utf-8")
    html = html.replace("__TEAM_DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    st.caption("Vertical teams, primaries and workstreams, linked to the active projects in the Portfolio tab. "
               "Click a person to see their projects by research bucket. Workstream projects come from each project's "
               "Workstream tag (set it in the Portfolio view's edit panel).")
    components.html(html, height=1200, scrolling=True)

if view == "👥 Team structure":
    render_team_structure()
    st.stop()

# ── Prioritization rubric view ───────────────────────────────────────────────
if view == "🧭 Prioritization rubric":
    st.html((Path(__file__).parent / "research_rubric.html").read_text(encoding="utf-8"))
    st.stop()

c1, c2 = st.columns([3, 1])
with c1:
    st.caption(f"{len(active)} active projects · {len(people)} people · grouped into 4 research buckets. "
               "Excludes Done & Sunsetted. Live from the project database.")
with c2:
    editor_sel = st.selectbox("Editing as", ["— view only —"] + EDITORS,
                              help="Select your name to make edits. Editing is limited to research leads.")
st.session_state.editor = editor_sel if editor_sel in EDITORS else ""
can_edit = st.session_state.editor in EDITORS

if can_edit:
    edit_mode = st.toggle("✏️ Edit mode", value=False,
                          help="Turn on to move projects between buckets and edit people, stage, or name.")
else:
    edit_mode = False
    st.caption("🔒 **View only.** Editing is limited to: " + ", ".join(EDITORS)
               + ". Choose your name in **Editing as** (top right) to make changes.")

f1, f2 = st.columns([3, 2])
person_filter = f1.multiselect("Highlight people", people, placeholder="Show everyone",
                               default=[focus_person] if focus_person in people else [],
                               help="Move projects with the selected people to the top and dim the rest.")
ws_filter = f2.multiselect("Highlight workstreams", WORKSTREAMS, placeholder="All workstreams",
                           default=[focus_ws] if focus_ws in WORKSTREAMS else [],
                           help="Move projects tagged with the selected workstreams to the top and dim the rest.")

# ── Collaboration view: who works together ───────────────────────────────────
def _collab_index(active_list):
    from collections import defaultdict
    pair = defaultdict(list)      # frozenset({a,b}) -> [project names]
    for p in active_list:
        team = dedupe_team((p.get("overview") or {}).get("team"))
        names = sorted({m["name"] for m in team if m["name"] in team_people})
        pname = (p.get("overview") or {}).get("name") or p["id"]
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                pair[frozenset((names[i], names[j]))].append(pname)
    return pair

def _dot_id(s):
    return '"' + str(s).replace('\\', '').replace('"', '') + '"'

with st.expander("🤝 Who's working together", expanded=False):
    pair = _collab_index(active)
    if not pair:
        st.caption("No shared-project collaborations found.")
    else:
        f1, f2 = st.columns([2, 2])
        focus = f1.selectbox("Focus on a person", ["— everyone —"] + team_people,
                             help="Show only this person and their collaborators.")
        focus = None if focus.startswith("—") else focus
        max_w = max(len(v) for v in pair.values())
        min_shared = f2.slider("Minimum shared projects (edge)", 1, max(2, max_w), 1,
                               help="Hide pairs who share fewer than this many active projects.")

        edges, nodes = [], set()
        for pr, projs in pair.items():
            w = len(projs)
            if w < min_shared:
                continue
            a, b = tuple(pr)
            if focus and focus not in (a, b):
                continue
            nodes.add(a); nodes.add(b)
            edges.append((a, b, w))
        if focus:
            nodes.add(focus)

        if not edges:
            st.info(("No co-workers" if focus else "No pairs") +
                    f" share ≥ {min_shared} active projects at this threshold.")
        else:
            dot = ["graph G {",
                   'graph [layout=neato, overlap=false, splines=true, bgcolor="transparent"];',
                   'node [shape=ellipse, style="filled", fillcolor="#eef1f5", color="#c7d0de", '
                   'fontname="Helvetica", fontsize=11, fontcolor="#1a2030"];',
                   'edge [color="#9aa6b8"];']
            for n in sorted(nodes):
                if focus and n == focus:
                    dot.append(f'{_dot_id(n)} [fillcolor="#5a5fc0", fontcolor="white", color="#5a5fc0"];')
                else:
                    dot.append(f'{_dot_id(n)} ;')
            for a, b, w in edges:
                pen = min(1 + (w - 1) * 0.9, 7)
                dot.append(f'{_dot_id(a)} -- {_dot_id(b)} [penwidth={pen:.1f}, '
                           f'label="{w if w > 1 else ""}", fontsize=9, fontcolor="#727d94"];')
            dot.append("}")
            st.graphviz_chart("\n".join(dot), use_container_width=True)
            st.caption("Each line links people who share an active project; thicker = more shared projects.")

            if focus:
                import pandas as pd
                rows = []
                for pr, projs in pair.items():
                    if focus in pr and len(projs) >= min_shared:
                        other = next(x for x in pr if x != focus)
                        rows.append({"Collaborator": other, "# shared": len(projs),
                                     "Shared projects": ", ".join(sorted(projs))})
                rows.sort(key=lambda r: (-r["# shared"], r["Collaborator"]))
                if rows:
                    st.markdown(f"**{focus}** works with **{len(rows)}** {'person' if len(rows)==1 else 'people'}:")
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

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
def is_dimmed(p):
    """True when a highlight filter is on and this project doesn't match it."""
    ov = p.get("overview") or {}
    names = [m["name"] for m in visible_team(dedupe_team(ov.get("team")))]
    return ((bool(person_filter) and not any(n in person_filter for n in names))
            or (bool(ws_filter) and ov.get("workstream") not in ws_filter))

filtering = bool(person_filter or ws_filter)
cols = st.columns(4)
for col, bucket in zip(cols, BUCKETS):
    # Highlighted projects first, then the rest; alphabetical within each group
    items = sorted([p for p in active if bucket_of(p) == bucket],
                   key=lambda p: (is_dimmed(p), ((p.get("overview") or {}).get("name") or p["id"]).lower()))
    n_match = sum(not is_dimmed(p) for p in items)
    color = BUCKET_COLOR[bucket]
    with col:
        count = f"{n_match} of {len(items)}" if filtering else f"{len(items)}"
        st.markdown(
            f"<div style='border-bottom:3px solid {color};padding-bottom:6px;margin-bottom:10px'>"
            f"<span style='font-weight:700'>{bucket}</span> "
            f"<span style='color:{color};font-family:monospace;float:right'>{count}</span></div>",
            unsafe_allow_html=True)
        for p in items:
            ov = p.get("overview") or {}
            pid = p["id"]
            name = ov.get("name") or pid
            stage = (p.get("process") or {}).get("stage")
            team = dedupe_team(ov.get("team"))           # full team, used by the edit panel
            shown_team = visible_team(team)              # hides inactive / unknown people on the card
            names = [m["name"] for m in team]
            ws = ov.get("workstream")
            dim = is_dimmed(p)
            opacity = "0.35" if dim else "1"

            def _pl(m):   # each name links to the board with that person highlighted
                nm = f"<b>{m['name']}</b>" if m["role"] == "Lead" else m["name"]
                return (f"<a href='?view=portfolio&person={quote(m['name'])}' target='_self' "
                        f"title='Highlight projects with {m['name']}' style='color:inherit;text-decoration:none'>{nm}</a>")
            leads = ", ".join(_pl(m) for m in shown_team) or "<i>No one assigned</i>"
            st.markdown(
                f"<div style='opacity:{opacity};border:1px solid #ddd;border-left:3px solid {color};"
                f"border-radius:10px;padding:9px 11px;margin-bottom:9px'>"
                f"<div style='font-weight:600;font-size:0.95rem'>{name}</div>"
                + (f"<a href='?view=team&ws={quote(ws)}' target='_self' title='See the {ws} workstream in Team structure' "
                   f"style='display:inline-block;margin-top:3px;font-size:0.7rem;font-weight:600;color:#fff;"
                   f"background:{WS_COLOR.get(ws, '#94a3b8')};border-radius:999px;padding:1px 8px;text-decoration:none'>"
                   f"{ws} ↗</a>" if ws else "") +
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
                    _ws_opts = ["— none —"] + WORKSTREAMS
                    new_ws = st.selectbox("Workstream", _ws_opts,
                                          index=_ws_opts.index(ws) if ws in WORKSTREAMS else 0, key=f"ws_{pid}",
                                          help="Links this project to a workstream on the Team structure tab.")

                    st.markdown("**Team**")
                    new_team = []
                    for i, m in enumerate(team):
                        t1, t2, t3 = st.columns([3, 3, 1])
                        _tag = "" if is_shown(m["name"]) else " <span style='color:#9aa6b8;font-size:0.8em'>(inactive)</span>"
                        t1.markdown(f"<div style='padding-top:6px'>{m['name']}{_tag}</div>", unsafe_allow_html=True)
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
                        nw = new_ws if new_ws in WORKSTREAMS else None
                        def _mut(pr):
                            pr.setdefault("overview", {})
                            pr["overview"]["name"] = nn
                            pr["overview"]["workstream"] = nw
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
                        if st.button("Yes, remove", key=f"yesrm_{pid}") and st.session_state.editor in EDITORS:
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
