from ad_dss.evaluation.esa_adb import EventInterval, evaluate_events, intervals_overlap, metrics_row


def test_intervals_overlap_when_prediction_intersects_truth() -> None:
    assert intervals_overlap(EventInterval("p1", 10, 12), EventInterval("a1", 12, 15))


def test_event_f0_5_weights_precision_over_recall() -> None:
    metrics = evaluate_events(
        predictions=[
            EventInterval("p1", 10, 12),
            EventInterval("p2", 50, 52),
        ],
        anomaly_truth=[
            EventInterval("a1", 11, 15),
            EventInterval("a2", 100, 110),
        ],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1
    assert metrics.precision == 0.5
    assert metrics.recall == 0.5
    assert metrics.f0_5 == 0.5


def test_event_metrics_handle_zero_predictions() -> None:
    metrics = evaluate_events(predictions=[], anomaly_truth=[EventInterval("a1", 1, 2)])

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.f0_5 == 0.0
    assert metrics.false_negatives == 1


def test_rare_nominal_events_are_counted_separately() -> None:
    metrics = evaluate_events(
        predictions=[EventInterval("p1", 20, 22)],
        anomaly_truth=[],
        rare_nominal_truth=[EventInterval("r1", 21, 25)],
    )

    assert metrics.false_positives == 1
    assert metrics.rare_nominal_events == 1
    assert metrics.rare_nominal_overlaps == 1


def test_metrics_row_includes_evidence_context() -> None:
    metrics = evaluate_events(
        predictions=[EventInterval("p1", 1, 2)],
        anomaly_truth=[EventInterval("a1", 1, 2)],
    )
    row = metrics_row(
        dataset="ESA-M1",
        model_version="zscore",
        configuration="default",
        metrics=metrics,
    )

    assert row["dataset"] == "ESA-M1"
    assert row["model_version"] == "zscore"
    assert row["event_f0_5"] == 1.0
