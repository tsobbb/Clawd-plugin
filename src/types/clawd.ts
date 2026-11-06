export interface PaletteItem {
  id: number;
  name: string;
  bodyColor: string;
  eyeColor: string;
}

export const PALETTES: PaletteItem[] = [
  { id: 0, name: "Claude (Оригинал)", bodyColor: "#D97757", eyeColor: "#1A1A1A" },
  { id: 1, name: "Claude Dark", bodyColor: "#383838", eyeColor: "#F5F5F5" },
  { id: 2, name: "Anthropic Spark", bodyColor: "#E06C38", eyeColor: "#1A1A1A" },
  { id: 3, name: "Мятный", bodyColor: "#4FBF98", eyeColor: "#12241D" },
  { id: 4, name: "Лавандовый", bodyColor: "#9B8AEE", eyeColor: "#1B1631" },
  { id: 5, name: "Небесный", bodyColor: "#4FA8E8", eyeColor: "#0E1C29" },
  { id: 6, name: "Сакура", bodyColor: "#EE85AE", eyeColor: "#2A1220" },
  { id: 7, name: "Киберпанк Неон", bodyColor: "#00E5FF", eyeColor: "#0A0A14" },
  { id: 8, name: "Золотой Слиток", bodyColor: "#FFD700", eyeColor: "#3E2723" },
  { id: 9, name: "Радужный RGB", bodyColor: "#FF0077", eyeColor: "#FFFFFF" },
  { id: 10, name: "Хамелеон (Тема)", bodyColor: "#2563EB", eyeColor: "#FFFFFF" },
];

export const HATS = [
  "Без шапки",
  "Наушники DJ",
  "Корона 👑",
  "Шерлок 🔍",
  "Ночной колпак",
  "Кошачьи ушки 🐱",
  "Цилиндр и Монокль 🎩",
  "Каска Сапёра ⛑",
  "Очки Thug Life 😎",
  "Шляпа Мага 🧙‍♂️",
  "Кепка назад",
] as const;

export type HatType = (typeof HATS)[number];

export type ExpressionType =
  | "open"
  | "blink"
  | "happy"
  | "surprised"
  | "dizzy"
  | "sleep"
  | "money"
  | "angry";

export interface LyricLine {
  timeSec: number;
  text: string;
}

export interface EatenItem {
  id: string;
  name: string;
  type: "edittext" | "message" | "header" | "avatar" | "button" | "generic";
  originalAlpha: number;
  w: number;
  h: number;
  timestamp: number;
}
