"""PROTOTYPE — THROWAWAY. Not production. No tests, no error handling, no polish.

Lives on branch `prototype/task-frontier-firewall-90`, never merged to main.

WHAT QUESTION THIS ANSWERS
    "You say the three pools of tasks can't leak into each other. Show me."

Run it:
    python prototypes/PROTOTYPE_firewall_walkthrough.py

Press Enter to step through. Every step prints the full state so you can watch
what changes. Nothing here calls a model. Nothing costs money. The database is
a scratch file in a temp folder, deleted on exit.
"""

import shutil
import sqlite3
import tempfile
from pathlib import Path

from skill_harness.storage.migrations import open_evidence
from skill_harness.task_frontier import (
    Arm,
    Observation,
    admit,
    audit_observation,
    load_manifest,
    matched_evidence,
)

# ---------------------------------------------------------------------------
# Plain-English names for the jargon, so the output is readable.
# ---------------------------------------------------------------------------

POOL_NAME = {
    "calibration": "DIFFICULTY-PICKING pool",
    "confirmation": "DOUBLE-CHECK pool",
    "matched": "SCORING pool",
}

# A "recipe" is what the code calls a semantic lineage: the template a task was
# generated from. Two tasks from one recipe are near-duplicates, so a recipe has
# to sit wholly inside one pool or the pools aren't really separate.
RECIPES = {
    "recipe-easy-lookup": "calibration",
    "recipe-nested-query": "confirmation",
    "recipe-multi-hop": "matched",
}

BAR = "=" * 78


def pause(prompt="   [Enter to continue] "):
    input(prompt)


def scene(number, title):
    print(f"\n{BAR}\n  SCENE {number} — {title}\n{BAR}")


def show_pools(conn, manifest, note=""):
    """The full state, after every action — what is sitting in each pool."""
    print(f"\n   STATE OF THE THREE POOLS{'  (' + note + ')' if note else ''}")
    for phase in ("calibration", "confirmation", "matched"):
        table = f"task_frontier_{phase}_obs"
        rows = conn.execute(
            f"SELECT observation_id, semantic_lineage_id, arm, passed FROM {table} ORDER BY observation_id"
        ).fetchall()
        print(f"\n   {POOL_NAME[phase]:<25} ({len(rows)} result{'s' if len(rows) != 1 else ''})")
        if not rows:
            print("       (empty)")
        for obs_id, recipe, arm, passed in rows:
            with_or_without = "WITH skill   " if arm == "full" else "WITHOUT skill"
            outcome = "passed" if passed else "failed"
            print(f"       {obs_id:<12} from {recipe:<20} {with_or_without}  {outcome}")

    scorer_sees = matched_evidence(conn, manifest)
    print(
        f"\n   >>> WHAT THE SCORER CAN SEE: {len(scorer_sees)} result(s) — "
        f"{[r.observation_id for r in scorer_sees]}"
    )


def record(conn, manifest, obs_id, recipe, arm, passed):
    """File one task result. The pool is decided here, at write time, and stamped on."""
    result = admit(
        conn,
        manifest,
        Observation(
            observation_id=obs_id,
            semantic_lineage_id=recipe,
            instance_id=f"task-{obs_id}",
            arm=arm,
            passed=passed,
            generator_fingerprint="gen-abc123",
            oracle_fingerprint="ora-def456",
            observed_at="2026-08-04T12:00:00+00:00",
        ),
    )
    if result.admissible:
        print(f"   filed {obs_id!r} (from {recipe}) -> {POOL_NAME[result.phase.value]}")
    else:
        print(f"   REFUSED {obs_id!r}: {result.reason}")
    return result


def build_manifest(assignments):
    """assignments: {recipe -> pool}. This is the frozen pre-registration."""
    partition = {"calibration": [], "confirmation": [], "matched": []}
    for recipe, pool in assignments.items():
        partition[pool].append(recipe)
    return load_manifest(
        {
            "task_family_id": "notes-search",
            "task_family_version": "1",
            "frozen_hashes": {
                "generator": "gen-abc123",
                "fixture": "fix-abc123",
                "oracle": "ora-def456",
                "harness": "har-abc123",
                "code": "cod-abc123",
            },
            "phase_partition": partition,
            "confirmation_attempt_budget": 2,
        }
    )


def main():
    workdir = Path(tempfile.mkdtemp(prefix="PROTOTYPE-wipe-me-"))
    conn = open_evidence(workdir / "scratch.db")

    print(f"""
{BAR}
  THE FIREWALL, WATCHED FROM OUTSIDE
{BAR}

  THE PROBLEM this exists to stop:

  To judge whether a skill helps, you compare tasks done WITH it against the
  same tasks done WITHOUT it. But first you have to choose how hard the tasks
  should be. If you choose the difficulty using the same tasks you later score
  on, you have flattered the skill -- you tuned the exam to the student, then
  reported the grade as proof they learned.

  THE FIX: three pools of tasks that can never mix.

     1. {POOL_NAME["calibration"]:<25} picks how hard the tasks should be
     2. {POOL_NAME["confirmation"]:<25} double-checks that choice on fresh tasks
     3. {POOL_NAME["matched"]:<25} the ONLY pool that scores the skill

  Scratch database: {workdir}
  (deleted when this exits -- nothing here touches your real evidence store)
""")
    pause()

    # -----------------------------------------------------------------------
    scene(1, "The pre-registration: which recipe goes in which pool")
    print("""
   You declare this UP FRONT, before any results exist. Three task recipes,
   one pool each. Once declared it is frozen -- that is the whole point.
""")
    manifest = build_manifest(RECIPES)
    for recipe, pool in RECIPES.items():
        print(f"   {recipe:<22} -> {POOL_NAME[pool]}")
    show_pools(conn, manifest, "nothing recorded yet")
    pause()

    # -----------------------------------------------------------------------
    scene(2, "Record some results. Watch where each one lands.")
    print("""
   Nobody chooses a pool here. The recipe decides it, by looking it up in the
   frozen pre-registration above.
""")
    record(conn, manifest, "obs-01", "recipe-easy-lookup", Arm.NULL, True)
    record(conn, manifest, "obs-02", "recipe-easy-lookup", Arm.NULL, False)
    record(conn, manifest, "obs-03", "recipe-nested-query", Arm.NULL, True)
    record(conn, manifest, "obs-04", "recipe-multi-hop", Arm.FULL, True)
    record(conn, manifest, "obs-05", "recipe-multi-hop", Arm.NULL, False)
    show_pools(conn, manifest)
    print("""
   Read the last line. The scorer sees TWO results -- the two from the scoring
   pool. The three difficulty-picking and double-check results exist, they are
   stored, they are auditable. The scorer just cannot reach them.
""")
    pause()

    # -----------------------------------------------------------------------
    scene(3, "ATTACK 1 — rewrite the pre-registration after the fact")
    print("""
   The obvious cheat: go back and say "actually, recipe-easy-lookup was a
   SCORING recipe all along", so its two results count toward the skill's
   score. Let's try it.
""")
    pause("   [Enter to run the attack] ")

    cheating_manifest = build_manifest(
        {
            "recipe-easy-lookup": "matched",  # <-- moved from difficulty-picking
            "recipe-nested-query": "confirmation",
            "recipe-multi-hop": "matched",
        }
    )
    print("   New (cheating) pre-registration says:")
    for recipe in RECIPES:
        print(f"   {recipe:<22} -> {POOL_NAME[cheating_manifest.phase_of(recipe).value]}")

    print("\n   Now ask the scorer what it can see, holding the CHEATING version:")
    show_pools(conn, cheating_manifest, "read through the cheating manifest")
    print("""
   ATTACK FAILED. Still two results. obs-01 and obs-02 did not move.

   WHY: the pool was decided when each result was WRITTEN, and stamped onto the
   record. It is not re-derived when you read. Rewriting the paperwork afterwards
   changes nothing about where the evidence already lives.

   Look up obs-01 directly -- no manifest involved, so the answer can only come
   from the stamp:""")
    stored = audit_observation(conn, "obs-01")
    print(f"\n       obs-01 is stamped: {POOL_NAME[stored.phase.value]}\n")
    pause()

    # -----------------------------------------------------------------------
    scene(4, "ATTACK 2 — edit the stored record directly in the database")
    print("""
   Fine, says the cheat: skip the paperwork, go straight to the database and
   change the stamp on obs-01. Let's try that too.
""")
    pause("   [Enter to run the attack] ")
    try:
        conn.execute(
            "UPDATE task_frontier_calibration_obs SET phase = 'matched' WHERE observation_id = 'obs-01'"
        )
        print("   !!! THE EDIT WENT THROUGH -- the firewall is broken !!!")
    except sqlite3.IntegrityError as exc:
        print(f"   ATTACK FAILED. The database refused it:\n\n       {exc}\n")
        print("""   WHY: these tables are append-only. You may add evidence; you may never
   edit or delete it. An audit trail you can quietly re-partition afterwards
   is not an audit trail.""")
    show_pools(conn, manifest, "unchanged")
    pause()

    # -----------------------------------------------------------------------
    scene(5, "ATTACK 3 — file a result nobody pre-registered")
    print("""
   Last try: invent a new recipe that was never declared, and file a result
   from it. Which pool would it even go in?
""")
    pause("   [Enter to run the attack] ")
    record(conn, manifest, "obs-99", "recipe-i-just-made-up", Arm.FULL, True)
    show_pools(conn, manifest, "obs-99 was NOT stored")
    print("""
   ATTACK FAILED, with a reason given rather than a silent drop. Off-manifest
   evidence has no pool it could honestly belong to, so it does not get one.
""")
    pause()

    # -----------------------------------------------------------------------
    scene(6, "The thing that is NOT proven here")
    print("""
   Being straight about the limits, because overclaiming is the failure mode
   this whole tool exists to avoid:

   PROVEN ABOVE
     - a result's pool is fixed at the moment it is written
     - rewriting the pre-registration afterwards moves nothing
     - the stored record cannot be edited or deleted
     - unregistered evidence is refused with a reason

   NOT PROVEN, AND NOT BUILT YET
     - that the scoring pool actually FEEDS the scorer (ticket #91 -- right now
       it hands over raw results, not the paired win/loss counts the maths needs)
     - that a "fresh" recipe is genuinely fresh and not a reworded clone of a
       difficulty-picking one (ticket #92)
     - the full end-to-end no-leak proof on synthetic data (ticket #94)

   So: this removes a whole class of leak -- the kind where somebody forgets a
   filter. It is not a claim that the measurement is now trustworthy end to end.
   Three tickets stand between here and that.
""")

    conn.close()
    shutil.rmtree(workdir, ignore_errors=True)
    print(f"{BAR}\n  Scratch database deleted. Nothing persisted.\n{BAR}\n")


if __name__ == "__main__":
    main()
