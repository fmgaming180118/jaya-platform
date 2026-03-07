import pathlib

p = pathlib.Path(r"d:\Kampus\coba-coba\jaya-research\JAYA_CORE\src\brain_v2\organism\homeostasis.py")
content = p.read_text(encoding="utf-8")

old = (
    '            twin.planner.push(Task(\n'
    '                priority=int(Priority.CRITICAL),\n'
    '                label="REPAIR",\n'
    '                code=(\n'
    '                    "# Homeostasis-triggered repair\\n"\n'
    '                    "# Inspect last failure, reset problematic state.\\n"\n'
    '                    "score = 0.5   # baseline health signal\\n"\n'
    '                ),\n'
    '                meta={"reason": reason, "alert": self._alert_count},\n'
    '            ))'
)

new = (
    '            # V18: smart REPAIR based on severity\n'
    '            if avg_score < self.min_avg_score and error_rate > self.max_error_rate:\n'
    '                # Both degraded: evolve weights + meta-reflect\n'
    '                repair_code = (\n'
    '                    "from src.brain_v2.education.live_evolver import LiveEvolver\\n"\n'
    '                    "evolver = LiveEvolver(engine, max_steps=300)\\n"\n'
    '                    "result = evolver.run_evolution(300)\\n"\n'
    '                    "score = min(1.0, 0.4 + result[\'delta_fitness\'] * 2)\\n"\n'
    '                )\n'
    '            elif error_rate > self.max_error_rate:\n'
    '                # High error rate: curriculum self-study\n'
    '                repair_code = (\n'
    '                    "from src.brain_v2.engine.self_bootstrap import SelfBootstrap\\n"\n'
    '                    "sb = SelfBootstrap()\\n"\n'
    '                    "tasks = sb.generate_curriculum(twin)\\n"\n'
    '                    "score = 0.6 if tasks else 0.4\\n"\n'
    '                )\n'
    '            else:\n'
    '                # Low score: light weight evolution\n'
    '                repair_code = (\n'
    '                    "from src.brain_v2.education.live_evolver import LiveEvolver\\n"\n'
    '                    "evolver = LiveEvolver(engine, max_steps=150)\\n"\n'
    '                    "result = evolver.run_evolution(150)\\n"\n'
    '                    "score = min(1.0, 0.5 + result[\'delta_fitness\'])\\n"\n'
    '                )\n'
    '            twin.planner.push(Task(\n'
    '                priority=int(Priority.CRITICAL),\n'
    '                label="REPAIR",\n'
    '                code=repair_code,\n'
    '                meta={"reason": reason, "alert": self._alert_count},\n'
    '            ))'
)

assert old in content, f"OLD not found!\n---\n{old}\n---"
content = content.replace(old, new)
p.write_text(content, encoding="utf-8")
print("homeostasis.py updated OK")
