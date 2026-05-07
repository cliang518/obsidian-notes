import { reactive } from "vue";

const TOKEN_KEY = "yj_v2_access_token";
const USER_KEY = "yj_v2_user";

export const authState = reactive({
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: loadUser(),
  ready: false,
});

function loadUser() {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    console.warn("Failed to parse stored auth user.", error);
    return null;
  }
}

export function setAuthSession(token, user) {
  authState.token = token || "";
  authState.user = user || null;
  authState.ready = true;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

export function clearAuthSession() {
  setAuthSession("", null);
}

export function markAuthReady() {
  authState.ready = true;
}

export function getAuthToken() {
  return authState.token || "";
}

