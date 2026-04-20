const API_ROOT = window.location.origin;

function toInt(value, fallback = 0) {
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function toFloat(value, fallback = 0) {
  const parsed = Number.parseFloat(value);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function normalizeMission(raw) {
  const distance = toFloat(raw.distance_traveled, 0);
  return {
    sessionId: String(raw.session_id || ""),
    robotId: String(raw.robot_id || ""),
    missionType: String(raw.mission_type || ""),
    missionResult: String(raw.mission_result || "Unknown"),
    startTime: String(raw.start_time || "0"),
    endTime: String(raw.end_time || "0"),
    abortReason: String(raw.abort_reason || ""),
    moves: {
      total: toInt(raw.moves_total, 0),
      left: toInt(raw.moves_left_turn, 0),
      right: toInt(raw.moves_right_turn, 0),
      forward: toInt(raw.moves_straight, 0),
      reverse: toInt(raw.moves_reverse, 0)
    },
    durationSeconds: toInt(raw.duration_seconds, 0),
    distanceMeters: distance
  };
}

export async function fetchSessions() {
  const response = await fetch(`${API_ROOT}/sessions`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sessions (${response.status})`);
  }

  const payload = await response.json();
  const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
  return sessions.map((session) => ({
    sessionId: String(session.session_id || ""),
    robotId: String(session.robot_id || ""),
    missionResult: String(session.mission_result || ""),
    movesTotal: toInt(session.moves_total, 0),
    durationSeconds: toInt(session.duration_seconds, 0)
  }));
}

export async function fetchMission(sessionId) {
  if (!sessionId) {
    throw new Error("Missing session ID");
  }

  const response = await fetch(`${API_ROOT}/mission/${encodeURIComponent(sessionId)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch mission (${response.status})`);
  }

  const payload = await response.json();
  return normalizeMission(payload);
}
