import React, { useState } from 'react';
import {
    MenuFoldOutlined,
    MenuUnfoldOutlined,
    DashboardOutlined,
    UserOutlined,
    TableOutlined,
    ProjectOutlined,
    LogoutOutlined,
    BulbOutlined,
    SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Layout, Menu, Button, theme, Dropdown, Avatar, Space } from 'antd';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { authService } from '../../services/auth';

const { Header, Sider, Content } = Layout;

const AppLayout: React.FC = () => {
    const [collapsed, setCollapsed] = useState(false);
    const {
        token: { colorBgContainer, borderRadiusLG },
    } = theme.useToken();

    const navigate = useNavigate();
    const location = useLocation();
    const user = authService.getCurrentUser();

    const handleLogout = () => {
        authService.logout();
        navigate('/login');
    };

    const menuItems = [
        {
            key: '/dashboard',
            icon: <DashboardOutlined />,
            label: 'Dashboard',
        },
        {
            key: '/users',
            icon: <UserOutlined />,
            label: 'User Management',
        },
        {
            key: '/schema',
            icon: <TableOutlined />,
            label: 'Schema Explorer',
        },
        {
            key: '/mappings',
            icon: <ProjectOutlined />,
            label: 'Semantic Mappings',
        },
        {
            key: '/rules',
            icon: <SafetyCertificateOutlined />,
            label: 'Business Rules',
        },
        {
            key: '/examples',
            icon: <BulbOutlined />,
            label: 'Golden Examples',
        },
    ];

    const userMenu = {
        items: [
            {
                key: 'logout',
                label: 'Logout',
                icon: <LogoutOutlined />,
                onClick: handleLogout,
            }
        ]
    };

    return (
        <Layout style={{ minHeight: '100vh' }}>
            <Sider trigger={null} collapsible collapsed={collapsed}>
                <div style={{
                    height: 32,
                    margin: 16,
                    background: 'rgba(255, 255, 255, 0.2)',
                    textAlign: 'center',
                    lineHeight: '32px',
                    color: 'white',
                    fontWeight: 'bold'
                }}>
                    {collapsed ? 'NT' : 'NT Revenue Admin'}
                </div>
                <Menu
                    theme="dark"
                    mode="inline"
                    selectedKeys={[location.pathname]}
                    items={menuItems}
                    onClick={({ key }) => navigate(key)}
                />
            </Sider>
            <Layout>
                <Header style={{ padding: 0, background: colorBgContainer, display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingRight: 24 }}>
                    <Button
                        type="text"
                        icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                        onClick={() => setCollapsed(!collapsed)}
                        style={{
                            fontSize: '16px',
                            width: 64,
                            height: 64,
                        }}
                    />

                    <Dropdown menu={userMenu}>
                        <Space style={{ cursor: 'pointer' }}>
                            <Avatar icon={<UserOutlined />} />
                            <span>{user?.display_name || 'Admin'}</span>
                        </Space>
                    </Dropdown>
                </Header>
                <Content
                    style={{
                        margin: '24px 16px',
                        padding: 24,
                        minHeight: 280,
                        background: colorBgContainer,
                        borderRadius: borderRadiusLG,
                    }}
                >
                    <Outlet />
                </Content>
            </Layout>
        </Layout>
    );
};

export default AppLayout;
