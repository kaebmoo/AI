import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ActivityIndicator, KeyboardAvoidingView, Platform, Alert } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { authService } from '../../services/auth';
import { useAuth } from '../../context/AuthContext';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

export default function VerifyScreen() {
    const { email } = useLocalSearchParams<{ email: string }>();
    const [otp, setOtp] = useState('');
    const [loading, setLoading] = useState(false);
    const { signIn } = useAuth();
    const router = useRouter();

    const handleVerify = async () => {
        if (!otp || otp.length < 6) {
            Alert.alert('Error', 'Please enter a valid 6-digit OTP');
            return;
        }

        setLoading(true);
        try {
            if (!email) throw new Error('Email missing');
            const response = await authService.verify(email, otp);

            // Sign in via context (sets token and handles redirect)
            if (response && response.access_token) {
                console.log('[VerifyScreen] Verification success, signing in with token:', response.access_token);
                await signIn(response.access_token);
            } else {
                console.error('[VerifyScreen] No token in response', response);
                throw new Error('No access token received');
            }
        } catch (error: any) {
            const msg = error.response?.data?.detail || error.message || 'Verification failed';
            Alert.alert('Error', msg);
        } finally {
            setLoading(false);
        }
    };

    const handleResend = async () => {
        // Implement resend logic (call login again)
        try {
            if (!email) return;
            await authService.login(email);
            Alert.alert("Success", "OTP Resent");
        } catch (e: any) {
            Alert.alert("Notice", e.response?.data?.detail || "Please wait before retrying");
        }
    }

    return (
        <SafeAreaView className="flex-1 bg-gray-50 dark:bg-gray-900 justify-center px-6">
            <KeyboardAvoidingView
                behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
                className="w-full max-w-md mx-auto"
            >
                <TouchableOpacity onPress={() => router.back()} className="mb-8">
                    <Ionicons name="arrow-back" size={24} className="text-gray-900 dark:text-gray-100" />
                </TouchableOpacity>

                <View className="items-center mb-10">
                    <View className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full items-center justify-center mb-4">
                        <Ionicons name="shield-checkmark" size={32} className="text-green-600 dark:text-green-400" color="#16a34a" />
                    </View>
                    <Text className="text-3xl font-bold text-gray-900 dark:text-gray-100">Verify OTP</Text>
                    <Text className="text-gray-500 dark:text-gray-400 mt-2 text-center">
                        Enter the 6-digit code sent to
                    </Text>
                    <Text className="text-gray-700 dark:text-gray-300 font-medium text-center">
                        {email}
                    </Text>
                </View>

                <View className="space-y-6">
                    <View>
                        <Text className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1 ml-1 pl-1">OTP Code</Text>
                        <TextInput
                            className="w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3.5 text-center text-2xl tracking-widest text-gray-900 dark:text-gray-100"
                            placeholder="000000"
                            placeholderTextColor="#9CA3AF"
                            value={otp}
                            onChangeText={setOtp}
                            keyboardType="number-pad"
                            maxLength={6}
                            autoFocus
                        />
                    </View>

                    <TouchableOpacity
                        onPress={handleVerify}
                        disabled={loading}
                        className={`w-full bg-blue-600 rounded-xl py-4 items-center shadow-lg shadow-blue-500/20 active:opacity-90 ${loading ? 'opacity-70' : ''}`}
                    >
                        {loading ? (
                            <ActivityIndicator color="white" />
                        ) : (
                            <Text className="text-white font-semibold text-lg">Verify & Login</Text>
                        )}
                    </TouchableOpacity>

                    <TouchableOpacity onPress={handleResend} className="items-center mt-4">
                        <Text className="text-blue-600 dark:text-blue-400 font-medium">Resend Code</Text>
                    </TouchableOpacity>
                </View>
            </KeyboardAvoidingView>
        </SafeAreaView>
    );
}
