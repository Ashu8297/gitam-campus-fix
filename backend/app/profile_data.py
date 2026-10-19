from .models import Role, User

STUDENT_REQUIRED = (
    "username",
    "department",
    "branch",
    "year_of_study",
    "semester",
    "contact_number",
)
STAFF_REQUIRED = ("contact_number", "work_category")
ADMIN_REQUIRED = ("contact_number",)


def profile_completion(user: User) -> tuple[int, list[str]]:
    if user.role == Role.student:
        profile = user.student_profile
        fields = {
            "full_name": user.full_name,
            "email": user.email,
            "registration_number": profile.registration_number if profile else None,
            **(
                {name: getattr(profile, name) for name in STUDENT_REQUIRED}
                if profile
                else {name: None for name in STUDENT_REQUIRED}
            ),
        }
        required = ("full_name", "email", "registration_number", *STUDENT_REQUIRED)
    elif user.role == Role.staff:
        profile = user.staff_profile
        fields = {
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": profile.staff_id if profile else None,
            "contact_number": profile.contact_number if profile else None,
            "work_category": profile.work_category if profile else None,
        }
        required = ("full_name", "email", "staff_id", "contact_number", "work_category")
    else:
        fields = {
            "full_name": user.full_name,
            "email": user.email,
            "contact_number": user.contact_number,
        }
        required = ("full_name", "email", *ADMIN_REQUIRED)
    missing = [name for name in required if not fields.get(name)]
    percentage = round(100 * (len(required) - len(missing)) / len(required))
    return percentage, missing


def profile_response(user: User) -> dict:
    completion, missing = profile_completion(user)
    profile = user.student_profile if user.role == Role.student else user.staff_profile
    result = {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.value,
        "profile_photo_url": user.profile_photo_url,
        "completion": completion,
        "missing": missing,
    }
    if user.role == Role.student:
        result.update({
            "registration_number": profile.registration_number if profile else None,
            "username": profile.username if profile else None,
            "department": profile.department if profile else None,
            "branch": profile.branch if profile else None,
            "year_of_study": profile.year_of_study if profile else None,
            "semester": profile.semester if profile else None,
            "contact_number": profile.contact_number if profile else None,
        })
    elif user.role == Role.staff:
        result.update({
            "staff_id": profile.staff_id if profile else None,
            "work_category": profile.work_category if profile else None,
            "contact_number": profile.contact_number if profile else None,
        })
    else:
        result["contact_number"] = user.contact_number
    return result
