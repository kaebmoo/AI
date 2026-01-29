import React from 'react'
import { Card, Statistic, Row, Col, Spin, Alert } from 'antd'
import { ArrowUpOutlined, UserOutlined, DatabaseOutlined, FileTextOutlined, TableOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'

interface DashboardStats {
    total_users: number
    total_mappings: number
    total_rules: number
    total_columns: number
}

const getStats = async () => {
    const response = await api.get<DashboardStats>('/admin/stats');
    return response.data;
};

const Dashboard: React.FC = () => {
    const { data: stats, isLoading, error } = useQuery({
        queryKey: ['dashboard_stats'],
        queryFn: getStats
    });

    if (isLoading) {
        return <div style={{ textAlign: 'center', marginTop: 50 }}><Spin size="large" /></div>;
    }

    if (error) {
        return <Alert message="Error loading dashboard stats" type="error" />;
    }

    return (
        <div>
            <h2>Dashboard</h2>

            <Row gutter={16}>
                <Col span={6}>
                    <Card bordered={false}>
                        <Statistic
                            title="Total Users"
                            value={stats?.total_users}
                            valueStyle={{ color: '#3f8600' }}
                            prefix={<UserOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false}>
                        <Statistic
                            title="Mappings"
                            value={stats?.total_mappings}
                            valueStyle={{ color: '#cf1322' }}
                            prefix={<FileTextOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false}>
                        <Statistic
                            title="Rules"
                            value={stats?.total_rules}
                            prefix={<DatabaseOutlined />}
                        />
                    </Card>
                </Col>
                <Col span={6}>
                    <Card bordered={false}>
                        <Statistic
                            title="Schema Columns"
                            value={stats?.total_columns}
                            prefix={<TableOutlined />}
                        />
                    </Card>
                </Col>
            </Row>

            <div style={{ marginTop: 24 }}>
                <p>System status: <strong>Online</strong></p>
                <p>AI Provider: <strong>Gemini 2.0 Flash</strong></p>
                <p style={{ color: '#888', fontSize: '12px' }}>Real-time data from database.</p>
            </div>
        </div>
    )
}

export default Dashboard
