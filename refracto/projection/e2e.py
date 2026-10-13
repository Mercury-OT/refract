"""Live e2e: primitive UI actions and explicit API actions share one core loop."""
from refracto.projection import backend, ui_stepwise
from refracto.projection.frontend import _eval_frontend, _eval_request_shape


def run(scenario, *, auth, ui, state, recorder, normalizer, api=None,
        resolve_request=None, poll_config=None, now=None, sleep=None):
    return ui_stepwise.run(
        scenario, projection="e2e", mode="live", auth=auth, ui=ui,
        state=state, recorder=recorder, normalizer=normalizer, api=api,
        resolve_request=resolve_request, eval_frontend=_eval_frontend,
        eval_request_shape=_eval_request_shape, eval_response=backend._eval_response,
        poll_config=poll_config, now=now, sleep=sleep,
    )
