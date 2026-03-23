# Requirements Document

## Introduction

A local desktop application that enables soccer coaches, analysts, and enthusiasts to analyze individual player performance from raw game footage. Users can upload a video file or provide a URL (YouTube, Veo, or other platforms), identify a specific player to track, and receive automatically generated statistics including touches, passes, ball losses, and position-based advanced metrics.

## Glossary

- **Application**: The local soccer game analysis desktop application
- **Footage**: A video file of a soccer match, either uploaded locally or sourced from a URL
- **Player**: A specific individual on the field to be tracked during analysis
- **Tracker**: The computer vision component responsible for detecting and following a player across video frames
- **Analyzer**: The component responsible for computing statistics from tracked player data
- **Stats_Report**: The structured output containing all computed statistics for a tracked player
- **Touch**: Any moment a tracked player makes contact with the ball
- **Pass**: A deliberate ball transfer from the tracked player to a teammate that reaches its target
- **Ball_Loss**: An event where the tracked player loses possession of the ball to an opponent
- **Position**: The tactical role of the tracked player on the field (e.g., goalkeeper, defender, midfielder, forward)
- **Advanced_Stats**: Position-specific metrics computed in addition to the core statistics
- **Frame**: A single image extracted from the video at a given point in time
- **Downloader**: The component responsible for fetching video content from remote URLs
- **JerseyColor**: The dominant color of a player's jersey, represented as a human-readable color name (e.g., "red", "blue", "white"), used as a supplementary player identification signal alongside jersey number
- **YouTubeAuth**: The OAuth2-based authentication state that grants the application access to a user's YouTube account, enabling download of unlisted or private videos
- **UploadStore**: The local directory (`~/.soccer-tracker/uploads/`) where uploaded video files are stored on disk

---

## Requirements

### Requirement 1: Video Input — Local File Upload

**User Story:** As a coach, I want to upload a local video file of a soccer match, so that I can analyze player performance from footage I already have.

#### Acceptance Criteria

1. THE Application SHALL accept video file uploads in MP4, MOV, AVI, and MKV formats.
2. WHEN a user selects a local video file, THE Application SHALL validate that the file format is supported before beginning analysis.
3. IF an unsupported file format is provided, THEN THE Application SHALL display a descriptive error message specifying the accepted formats.
4. IF a selected file cannot be read or is corrupted, THEN THE Application SHALL display an error message and allow the user to select a different file.
5. WHEN a valid video file is selected, THE Application SHALL display the video duration and resolution to the user before analysis begins.

---

### Requirement 2: Video Input — URL Import

**User Story:** As an analyst, I want to provide a URL from YouTube, Veo, or other platforms, so that I can analyze footage without downloading it manually. I also want to connect my YouTube account so I can access unlisted videos.

#### Acceptance Criteria

1. THE Application SHALL accept URLs from YouTube, Veo, and other publicly accessible video platforms.
2. THE Downloader SHALL support publicly accessible URLs by default, without requiring authentication.
3. WHEN a URL is submitted, THE Downloader SHALL fetch and cache the video locally before analysis begins.
4. IF a URL is malformed or points to an unsupported platform, THEN THE Application SHALL display a descriptive error message.
5. IF the remote video is unavailable or access is restricted without authentication, THEN THE Application SHALL display an error message indicating the reason for failure.
6. IF the URL requires authentication and the user has not connected their YouTube account, THEN THE Downloader SHALL return an UnavailableSourceError with a reason indicating that authentication is required.
7. WHILE the Downloader is fetching a remote video, THE Application SHALL display a progress indicator showing download status.
8. WHEN the download completes successfully, THE Application SHALL display the video duration and resolution before analysis begins.
9. THE Application SHALL provide a "Connect YouTube" button that initiates a Google OAuth2 flow to authorize access to the user's YouTube account.
10. WHEN the user completes the OAuth2 flow, THE Application SHALL store the access token locally at `~/.soccer-tracker/auth.json` and display a "Connected" status.
11. WHEN a YouTube account is connected, THE Downloader SHALL use the stored credentials to download unlisted videos accessible to that account.
12. THE Application SHALL allow the user to disconnect their YouTube account, which SHALL delete the stored token and revert to unauthenticated access.
13. IF the stored YouTube token is expired or invalid, THEN THE Application SHALL prompt the user to re-authenticate before attempting a download.

---

### Requirement 3: Player Identification

**User Story:** As a coach, I want to identify a specific player to track, so that the analysis focuses only on that individual.

#### Acceptance Criteria

1. WHEN a video is loaded, THE Application SHALL present the user with a mechanism to identify the target player.
2. THE Application SHALL support player identification by jersey number.
3. THE Application SHALL support player identification by selecting the player visually on the currently displayed video frame (for example after play/pause scrubbing).
4. THE Application SHALL support player identification by jersey color as a supplementary signal alongside jersey number.
5. WHEN a player is identified by jersey number, THE Tracker SHALL locate the player wearing that number in the video.
6. WHEN a jersey color is provided alongside a jersey number, THE Tracker SHALL use HSV color histogram matching on detected player bounding boxes to improve identification accuracy.
7. WHEN a player is identified by visual selection, THE Tracker SHALL use the selected region as the initial reference for tracking.
8. IF the Tracker cannot locate the identified player in the video, THEN THE Application SHALL notify the user and prompt for re-identification.
9. WHILE tracking is active, THE Tracker SHALL maintain a confidence score for each frame indicating tracking reliability.
10. IF the Tracker confidence score drops below 0.5 for more than 30 consecutive frames, THEN THE Application SHALL alert the user that tracking may have been lost.

---

### Requirement 4: Core Statistics — Touches

**User Story:** As a coach, I want to see how many times a player touched the ball, so that I can assess their involvement in the game.

#### Acceptance Criteria

1. THE Analyzer SHALL count each distinct ball contact made by the tracked player as one touch.
2. WHEN two ball contacts occur within 500 milliseconds by the same player, THE Analyzer SHALL count them as a single touch.
3. THE Stats_Report SHALL include the total touch count for the tracked player.
4. THE Stats_Report SHALL include a timestamp for each touch event.

---

### Requirement 5: Core Statistics — Passes

**User Story:** As a coach, I want to know how many successful passes a player made, so that I can evaluate their distribution quality.

#### Acceptance Criteria

1. THE Analyzer SHALL count a pass as successful when the ball travels from the tracked player to a teammate and the teammate receives possession.
2. THE Stats_Report SHALL include the total number of successful passes.
3. THE Stats_Report SHALL include the total number of attempted passes.
4. THE Stats_Report SHALL include the pass completion percentage, calculated as (successful passes / attempted passes) × 100, rounded to one decimal place.
5. IF the tracked player makes zero pass attempts, THEN THE Stats_Report SHALL display pass completion percentage as "N/A".

---

### Requirement 6: Core Statistics — Ball Losses

**User Story:** As a coach, I want to see how many times a player lost the ball, so that I can identify areas for improvement in ball retention.

#### Acceptance Criteria

1. THE Analyzer SHALL count a ball loss when the tracked player loses possession to an opponent through a tackle, interception, or miscontrol.
2. THE Stats_Report SHALL include the total number of ball losses.
3. THE Stats_Report SHALL include a timestamp for each ball loss event.
4. THE Stats_Report SHALL include the ball retention rate, calculated as ((touches - ball_losses) / touches) × 100, rounded to one decimal place.
5. IF the tracked player records zero touches, THEN THE Stats_Report SHALL display ball retention rate as "N/A".

---

### Requirement 7: Advanced Statistics by Position

**User Story:** As an analyst, I want position-specific advanced stats, so that I can evaluate a player against the expectations of their role.

#### Acceptance Criteria

1. THE Application SHALL prompt the user to specify the tracked player's position before generating advanced statistics.
2. THE Application SHALL support the following positions: Goalkeeper, Defender, Midfielder, and Forward.
3. WHERE the tracked player's position is Goalkeeper, THE Analyzer SHALL compute: saves, goals conceded, distribution accuracy, and sweeper actions.
4. WHERE the tracked player's position is Defender, THE Analyzer SHALL compute: tackles attempted, tackles won, interceptions, clearances, and aerial duels won.
5. WHERE the tracked player's position is Midfielder, THE Analyzer SHALL compute: key passes, through balls, distance covered (in meters), and ball recoveries.
6. WHERE the tracked player's position is Forward, THE Analyzer SHALL compute: shots on target, shots off target, dribbles attempted, dribbles completed, and off-ball runs.
7. THE Stats_Report SHALL include all applicable advanced statistics for the specified position.

---

### Requirement 8: Stats Report Output

**User Story:** As a coach, I want to export the analysis results, so that I can share them with players and staff.

#### Acceptance Criteria

1. WHEN analysis is complete, THE Application SHALL display the Stats_Report in the application UI.
2. THE Application SHALL allow the user to export the Stats_Report as a PDF file.
3. THE Application SHALL allow the user to export the Stats_Report as a JSON file.
4. WHEN exporting, THE Application SHALL include the video source reference, player identifier, and analysis timestamp in the Stats_Report.
5. IF an export operation fails, THEN THE Application SHALL display an error message and retain the Stats_Report in the UI.

---

### Requirement 9: Analysis Processing

**User Story:** As a user, I want to know the progress of the analysis, so that I can plan my time while waiting for results.

#### Acceptance Criteria

1. WHEN analysis begins, THE Application SHALL display a progress indicator showing the percentage of video frames processed.
2. THE Application SHALL process video at a minimum rate of 10 frames per second on standard hardware.
3. WHILE analysis is running, THE Application SHALL allow the user to cancel the operation.
4. WHEN the user cancels analysis, THE Application SHALL stop processing and discard partial results within 3 seconds.
5. WHEN analysis completes, THE Application SHALL display the total processing time.

---

### Requirement 10: Data Persistence

**User Story:** As a coach, I want previous analysis sessions to be saved, so that I can review past results without re-running the analysis.

#### Acceptance Criteria

1. WHEN analysis completes successfully, THE Application SHALL save the Stats_Report to local storage.
2. THE Application SHALL display a list of previously saved analysis sessions on the home screen.
3. WHEN a user selects a past session, THE Application SHALL load and display the corresponding Stats_Report.
4. THE Application SHALL allow the user to delete a saved session.
5. IF local storage is unavailable or full, THEN THE Application SHALL notify the user and offer to export the Stats_Report before discarding it.

---

### Requirement 11: Upload Storage Management

**User Story:** As a user, I want to clear all uploaded video files from local storage, so that I can free up disk space without manually navigating the filesystem.

#### Acceptance Criteria

1. THE Application SHALL display a "Clear Uploads" button in the UI that allows the user to delete all files stored in the UploadStore (`~/.soccer-tracker/uploads/`).
2. WHEN the user clicks "Clear Uploads", THE Application SHALL prompt for confirmation before deleting any files.
3. WHEN the user confirms, THE Application SHALL delete all files in the UploadStore and display a success message indicating how many files were removed.
4. IF the UploadStore is already empty, THE Application SHALL inform the user that there are no files to delete.
5. IF deletion fails for any file, THE Application SHALL display an error message identifying the failure and leave successfully deleted files removed.
6. THE Application SHALL expose a `DELETE /uploads` endpoint that performs the deletion server-side and returns the count of deleted files.

---

## Implementation Status Notes (Current Codebase)

These notes clarify where the current implementation is best-effort or partially enforced relative to the normative requirements above.

- **Requirement 9.2 (minimum 10 FPS):** current code reports progress and duration, but does not enforce a hard minimum FPS contract across hardware classes.
- **Requirement 9.4 (cancel + discard within 3 seconds):** cancellation is signaled immediately and the API waits up to about 3 seconds, but final stop timing still depends on where the pipeline is when cancellation is requested.
- **Requirement 10.5 (storage full flow):** persistence failures are surfaced, but there is no guaranteed user flow that always offers export before discard in every storage-failure path.
- **Requirement 2.13 (expired/invalid YouTube token prompt):** auth status and failures are exposed through API responses; explicit UI prompting/re-auth guidance is handled by frontend behavior rather than a strict backend-side guarantee.
