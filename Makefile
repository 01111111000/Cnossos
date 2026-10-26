PYTHON ?= python3
RUN_ID ?= main
# The live configuration; config/alt_cerebras.yaml is the D-052 alternate route.
CONFIG ?= config/main.yaml
RUN_DIR ?= results/$(RUN_ID)
MAIN ?= main
# results/synthetic is the tracked build provenance; a rerun must not collide with it.
SYNTHETIC_OUT ?= results/synthetic-rerun
LEGACY ?= config/legacy_r2.yaml
# The screen-disclosure design (D-044 to D-052), kept runnable (D-053 g).
SCREENS ?= config/screens.yaml
# D-046, D-050, D-053: the main run is played in two stages, split by the design's stage_one in the config;
# stage two refuses to start unless the stage-one record says PROCEED.
STAGE1 ?= $(shell $(PYTHON) -m tools.stages 1 --config $(CONFIG))
STAGE2 ?= $(shell $(PYTHON) -m tools.stages 2 --config $(CONFIG))
# A stage-one record for `make analyze PRIMARY=...` (default: the one in the run directory).
POSITIVE_CONTROL ?=
BUDGET_ARGS = $(if $(INPUT_PRICE),--input-price-per-million $(INPUT_PRICE)) $(if $(OUTPUT_PRICE),--output-price-per-million $(OUTPUT_PRICE)) $(if $(OUTPUT_TOKENS),--output-tokens $(OUTPUT_TOKENS))
.PHONY: test synthetic synthetic-legacy synthetic-screens smoke smoke-report stage1 positive-control stage2 replication resume merge main fallback fallback-p1 fallback-undercut analyze analyze-fallback facts figures figures-screens figures-legacy audit budget all

test:
	$(PYTHON) -m unittest discover -s tests -v
synthetic:
	$(PYTHON) -m analysis.synthetic --output $(SYNTHETIC_OUT)
synthetic-legacy:
	$(PYTHON) -m analysis.synthetic --config $(LEGACY) --output $(SYNTHETIC_OUT)-legacy
synthetic-screens:
	$(PYTHON) -m analysis.synthetic --config $(SCREENS) --output $(SYNTHETIC_OUT)-screens
smoke:
	$(PYTHON) -m run.cli --config $(CONFIG) --run-id $(RUN_ID) --live --smoke
main:
	$(PYTHON) -m run.cli --config $(CONFIG) --run-id $(RUN_ID) --live
stage1:
	$(PYTHON) -m run.cli --config $(CONFIG) --run-id $(RUN_ID)-s1 --live --prefix-ids $(STAGE1)
positive-control:
	$(PYTHON) -m tools.positive_control --run-dir results/$(RUN_ID)-s1
stage2:
	$(PYTHON) -m tools.positive_control --run-dir results/$(RUN_ID)-s1 --require-proceed
	$(PYTHON) -m run.cli --config $(CONFIG) --run-id $(RUN_ID)-s2 --live --prefix-ids $(STAGE2)
	$(PYTHON) -m tools.merge_runs --runs results/$(RUN_ID)-s1 results/$(RUN_ID)-s2 --output results/$(RUN_ID)
replication:
	$(PYTHON) -m run.cli --config config/replication.yaml --run-id $(RUN_ID) --live
fallback:
	$(MAKE) -j2 fallback-p1 fallback-undercut RUN_ID=$(RUN_ID)
fallback-p1:
	$(PYTHON) -m run.cli --config config/fallback_p1.yaml --run-id $(RUN_ID)-p1 --live
fallback-undercut:
	$(PYTHON) -m run.cli --config config/fallback_undercut.yaml --run-id $(RUN_ID)-undercut --live
analyze:
	$(PYTHON) -m analysis.pipeline --run-dir $(RUN_DIR) $(if $(PRIMARY),--primary $(PRIMARY)) $(if $(POSITIVE_CONTROL),--positive-control $(POSITIVE_CONTROL))
analyze-fallback:
	$(PYTHON) -m analysis.fallback --p1-run results/$(RUN_ID)-p1 --undercut-run results/$(RUN_ID)-undercut --output results/$(RUN_ID)-undercut/f1_verdict.json
resume:
	$(PYTHON) -m run.cli --config $(CONFIG) --run-id $(RUN_ID) --live --prefix-ids $(PREFIX_IDS)
merge:
	$(PYTHON) -m tools.merge_runs --runs $(addprefix results/,$(RUNS)) --output $(RUN_DIR)
smoke-report:
	$(PYTHON) -m tools.smoke_report --run-dir $(RUN_DIR)
facts:
	$(PYTHON) -m tools.facts --run-dir $(RUN_DIR)
figures:
	$(PYTHON) -m figures.swaps --run-dir $(RUN_DIR)
figures-screens:
	$(PYTHON) -m figures.screens --run-dir $(RUN_DIR)
figures-legacy:
	$(PYTHON) -m figures.primary --run-dir $(RUN_DIR)
	$(PYTHON) -m figures.interventions --run-dir $(RUN_DIR)
	$(PYTHON) -m figures.delta --run-dir $(RUN_DIR)
	$(PYTHON) -m figures.pareto --run-dir $(RUN_DIR)
	$(PYTHON) -m figures.undercut --run-dir $(RUN_DIR)
audit:
	$(PYTHON) -m tools.audit_observations --synthetic
budget:
	$(PYTHON) -m tools.estimate_cost --config $(CONFIG) $(BUDGET_ARGS)
	$(PYTHON) -m tools.estimate_cost --config $(CONFIG) --smoke $(BUDGET_ARGS)
	$(PYTHON) -m tools.estimate_cost --config config/fallback_p1.yaml $(BUDGET_ARGS)
	$(PYTHON) -m tools.estimate_cost --config config/fallback_undercut.yaml $(BUDGET_ARGS)
all: test synthetic synthetic-screens synthetic-legacy
