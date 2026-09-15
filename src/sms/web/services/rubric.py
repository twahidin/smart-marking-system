from pydantic import ValidationError

from sms.schemas.marking import Rubric
from sms.web.errors import ApiError


def parse_rubric(rubric_json: str) -> Rubric:
    try:
        rubric = Rubric.model_validate_json(rubric_json)
    except ValidationError as e:
        raise ApiError(400, "bad_rubric", f"Rubric is not valid: {e.errors()[0]['msg']}")
    if not rubric.criterion_defs:
        raise ApiError(400, "bad_rubric", "Add at least one criterion")
    return rubric
