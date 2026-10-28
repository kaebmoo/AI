import { Stack } from 'expo-router';
import React from 'react';

// ponytail: one screen — a single-tab bar was 50px of dead chrome on every viewport
export default function AppLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
