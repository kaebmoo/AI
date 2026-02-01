import React, { useState } from 'react'
import { Form, Input, Button, Card, Alert, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authService } from '../services/auth'

const Login: React.FC = () => {
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const navigate = useNavigate()

    const onFinish = async (values: any) => {
        setLoading(true)
        setError(null)

        try {
            const response = await authService.login({
                email: values.email,
                password: values.password,
                platform: 'web-admin'
            })

            // Store token
            localStorage.setItem('token', response.access_token)
            localStorage.setItem('user', JSON.stringify({
                email: response.user_email,
                display_name: response.display_name,
                role: response.role
            }))

            message.success('Login successful')
            navigate('/dashboard')
        } catch (err: any) {
            console.error("Login Error:", err); // Debug log
            if (err.response && err.response.data && err.response.data.detail) {
                setError(err.response.data.detail);
            } else {
                setError('Failed to login. Please check your credentials.');
            }
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100vh',
            backgroundColor: '#f0f2f5'
        }}>
            <Card title="NT AI Assistant Admin" style={{ width: 400 }}>
                {error && (
                    <Alert
                        message="Login Failed"
                        description={error}
                        type="error"
                        showIcon
                        style={{ marginBottom: 16 }}
                    />
                )}

                <Form
                    name="login"
                    initialValues={{ remember: true }}
                    onFinish={onFinish}
                    size="large"
                >
                    <Form.Item
                        name="email"
                        rules={[
                            { required: true, message: 'Please input your Email!' },
                            { type: 'email', message: 'Please enter a valid email!' }
                        ]}
                    >
                        <Input prefix={<UserOutlined />} placeholder="Email" />
                    </Form.Item>

                    <Form.Item
                        name="password"
                        rules={[{ required: true, message: 'Please input your Password!' }]}
                    >
                        <Input.Password prefix={<LockOutlined />} placeholder="Password" />
                    </Form.Item>

                    <Form.Item>
                        <Button type="primary" htmlType="submit" loading={loading} block>
                            Log in
                        </Button>
                    </Form.Item>
                </Form>
            </Card>
        </div>
    )
}

export default Login
