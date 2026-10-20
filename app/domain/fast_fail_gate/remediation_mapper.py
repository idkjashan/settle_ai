from typing import List, Optional
from app.domain.fast_fail_gate.schemas import (
    FastFailFailureCode,
    RemediationDirective,
    FastFailTelemetryDTO,
)

class RemediationMapper:
    def map_failures(
        self, codes: List[FastFailFailureCode], telemetry: Optional[FastFailTelemetryDTO] = None
    ) -> RemediationDirective:
        if not codes:
            return RemediationDirective(
                user_title="Verification Passed",
                user_message="All pre-checks passed successfully.",
                action_items=[],
                can_retry=False,
            )

        # Policy & Administrative Errors (Non-retryable)
        if FastFailFailureCode.POLICY_NOT_FOUND in codes:
            return RemediationDirective(
                user_title="Policy Not Found",
                user_message="We could not find an insurance policy matching the provided ID.",
                action_items=[
                    "Check your policy number and try again",
                    "Contact customer support if your policy was recently issued",
                ],
                can_retry=False,
            )

        if FastFailFailureCode.POLICY_INACTIVE in codes or FastFailFailureCode.POLICY_EXPIRED_OR_NOT_STARTED in codes:
            return RemediationDirective(
                user_title="Policy Coverage Inactive",
                user_message="Your insurance policy coverage is not active for today's date.",
                action_items=[
                    "Verify your policy coverage dates",
                    "Renew or activate your policy through your insurer portal",
                ],
                can_retry=False,
            )

        if FastFailFailureCode.ANNUAL_CASH_CLAIM_LIMIT_REACHED in codes:
            return RemediationDirective(
                user_title="Annual Instant Cash Limit Reached",
                user_message="You have already reached the maximum allowed instant cash claims for this policy year.",
                action_items=[
                    "File a standard claim with an authorized network garage",
                    "Contact your insurance representative for physical surveyor inspection",
                ],
                can_retry=False,
            )

        # Duplicate submission
        if FastFailFailureCode.DUPLICATE_VIDEO_SUBMISSION in codes:
            return RemediationDirective(
                user_title="Duplicate Video Detected",
                user_message="This exact video recording has already been submitted for a prior claim.",
                action_items=[
                    "Record a fresh, unbroken walkaround video of your vehicle's current damage",
                    "Do not reuse previously uploaded video files",
                ],
                can_retry=True,
            )

        # Metadata / Editing software
        if FastFailFailureCode.METADATA_EDITED_VIDEO in codes:
            editor = "editing software"
            if telemetry and telemetry.container_report and telemetry.container_report.detected_editor_tag:
                editor = telemetry.container_report.detected_editor_tag
            return RemediationDirective(
                user_title="Edited Video Rejected",
                user_message=f"The uploaded video contains metadata from non-linear editing software ({editor}).",
                action_items=[
                    "Record original, unedited video directly from your camera",
                    "Do not re-export through apps like CapCut, InShot, Premiere, or social media filters",
                ],
                can_retry=True,
            )

        # Quality & Container combinations
        action_items: List[str] = []
        messages: List[str] = []

        if FastFailFailureCode.INVALID_PHOTO_COUNT in codes:
            messages.append("Photo pack must contain between 3 and 6 photos")
            action_items.append("Submit 3 to 6 photos covering license plate, vehicle context, and damage closeup")

        if FastFailFailureCode.UNSUPPORTED_PHOTO_FORMAT in codes:
            messages.append("One or more photos are in an unsupported format")
            action_items.append("Upload photos in JPEG or PNG format")

        if FastFailFailureCode.RESOLUTION_TOO_LOW in codes:
            messages.append("Media resolution is below required quality standard")
            action_items.append("Switch camera settings to at least 720p or 1080p HD")

        if FastFailFailureCode.DURATION_TOO_SHORT in codes:
            messages.append("Video is too short (under 5 seconds)")
            action_items.append("Record a steady 15-second walkaround video")
        elif FastFailFailureCode.DURATION_TOO_LONG in codes:
            messages.append("Video exceeds 60 seconds")
            action_items.append("Keep the recording between 10 and 30 seconds focusing on the damaged panel")

        if FastFailFailureCode.FRAMERATE_TOO_LOW in codes:
            messages.append("Video framerate is under 15 FPS")
            action_items.append("Ensure your camera is set to record at 30 FPS")

        if FastFailFailureCode.VIDEO_TOO_DARK in codes or FastFailFailureCode.PHOTO_TOO_DARK in codes:
            messages.append("Lighting is too dark")
            action_items.append("Film or photograph in daylight or turn on your smartphone flashlight")
        elif FastFailFailureCode.VIDEO_TOO_BRIGHT in codes or FastFailFailureCode.PHOTO_TOO_BRIGHT in codes:
            messages.append("Lighting is overexposed or has direct blinding glare")
            action_items.append("Avoid capturing directly into bright headlights or direct sun")

        if FastFailFailureCode.VIDEO_TOO_BLURRY in codes or FastFailFailureCode.PHOTO_TOO_BLURRY in codes:
            messages.append("Media has significant blur")
            action_items.append("Hold the camera steady while capturing to avoid motion blur")

        if not messages:
            messages.append("Video failed technical sanity requirements")
            action_items.append("Please re-record a clear walkaround video and upload again")

        return RemediationDirective(
            user_title="Video Pre-Check Required Remediation",
            user_message=". ".join(messages) + ".",
            action_items=action_items,
            can_retry=True,
        )

remediation_mapper = RemediationMapper()

