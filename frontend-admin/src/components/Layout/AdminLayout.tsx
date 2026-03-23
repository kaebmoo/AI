import React, { useEffect, useRef, useState } from 'react';
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
    RobotOutlined,
    DatabaseOutlined,
    BuildOutlined,
    FileTextOutlined,
    SettingOutlined,
    CloudOutlined,
    ThunderboltOutlined,
    ApartmentOutlined,
    SwapOutlined,
    MessageOutlined,
    FileSearchOutlined,
    WarningOutlined,
    ForkOutlined,
    RocketOutlined,
    KeyOutlined
} from '@ant-design/icons';
import { Layout, Menu, Button, theme, Dropdown, Avatar, Space, Tag, Typography } from 'antd';
import { useNavigate, useLocation, Outlet } from 'react-router-dom';
import { authService } from '../../services/auth';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const MENU_STATE_KEY = 'nt-admin-open-keys';

const routeMeta: Record<string, { title: string; section: string }> = {
    '/dashboard': { title: 'Overview', section: 'Overview' },
    '/admin-agent': { title: 'Admin Agent', section: 'Overview' },
    '/providers': { title: 'AI Providers', section: 'AI Setup' },
    '/models': { title: 'AI Models', section: 'AI Setup' },
    '/settings': { title: 'Settings', section: 'AI Setup' },
    '/api-keys': { title: 'API Keys', section: 'AI Setup' },
    '/vanna-docs': { title: 'Vanna Knowledge', section: 'AI Setup' },
    '/analyzer': { title: 'Schema Analyzer', section: 'Data Setup' },
    '/schema': { title: 'Schema Explorer', section: 'Data Setup' },
    '/contexts': { title: 'Data Contexts', section: 'Data Setup' },
    '/context-onboarding': { title: 'Context Onboarding', section: 'Data Setup' },
    '/view-builder': { title: 'View Builder', section: 'Data Setup' },
    '/view-manager': { title: 'View Manager', section: 'Data Setup' },
    '/dimension-families': { title: 'Dimension Families', section: 'Data Setup' },
    '/hierarchy': { title: 'Master Data', section: 'Data Setup' },
    '/rules': { title: 'Business Rules', section: 'Data Setup' },
    '/mappings': { title: 'Semantic Mappings', section: 'Data Setup' },
    '/examples': { title: 'Golden Examples', section: 'Data Setup' },
    '/feedback': { title: 'Feedback', section: 'Monitoring' },
    '/query-logs': { title: 'Query Logs', section: 'Monitoring' },
    '/data-warnings': { title: 'Data Warnings', section: 'Monitoring' },
    '/query-patterns': { title: 'Query Patterns', section: 'Monitoring' },
    '/users': { title: 'User Management', section: 'System' },
};

const routeParents: Record<string, string[]> = {
    '/providers': ['ai-setup'],
    '/models': ['ai-setup'],
    '/settings': ['ai-setup'],
    '/api-keys': ['ai-setup'],
    '/vanna-docs': ['ai-setup'],
    '/analyzer': ['data-setup'],
    '/schema': ['data-setup'],
    '/contexts': ['data-setup'],
    '/context-onboarding': ['data-setup'],
    '/view-builder': ['data-setup'],
    '/view-manager': ['data-setup'],
    '/dimension-families': ['data-setup'],
    '/hierarchy': ['data-setup'],
    '/rules': ['data-setup'],
    '/mappings': ['data-setup'],
    '/examples': ['data-setup'],
    '/feedback': ['monitoring'],
    '/query-logs': ['monitoring'],
    '/data-warnings': ['monitoring'],
    '/query-patterns': ['monitoring'],
    '/users': ['system'],
};

const readStoredOpenKeys = () => {
    try {
        const raw = localStorage.getItem(MENU_STATE_KEY);
        return raw ? (JSON.parse(raw) as string[]) : [];
    } catch {
        return [];
    }
};

const persistOpenKeys = (keys: string[]) => {
    localStorage.setItem(MENU_STATE_KEY, JSON.stringify(keys));
};

const AppLayout: React.FC = () => {
    const [collapsed, setCollapsed] = useState(false);
    const [openKeys, setOpenKeys] = useState<string[]>(readStoredOpenKeys());
    const {
        token: { colorBgContainer, borderRadiusLG },
    } = theme.useToken();

    const navigate = useNavigate();
    const location = useLocation();
    const user = authService.getCurrentUser();
    const menuScrollRef = useRef<HTMLDivElement>(null);
    const contentScrollRef = useRef<HTMLDivElement>(null);

    const handleLogout = () => {
        authService.logout();
        navigate('/login');
    };

    const menuItems = [
        {
            key: '/dashboard',
            icon: <DashboardOutlined />,
            label: 'Overview',
        },
        {
            key: '/admin-agent',
            icon: <RobotOutlined />,
            label: 'Admin Agent',
        },
        {
            key: 'ai-setup',
            icon: <CloudOutlined />,
            label: 'AI Setup',
            children: [
                {
                    key: '/providers',
                    icon: <CloudOutlined />,
                    label: 'Providers',
                },
                {
                    key: '/models',
                    icon: <ThunderboltOutlined />,
                    label: 'Models',
                },
                {
                    key: '/settings',
                    icon: <SettingOutlined />,
                    label: 'Settings',
                },
                {
                    key: '/api-keys',
                    icon: <KeyOutlined />,
                    label: 'API Keys',
                },
                {
                    key: '/vanna-docs',
                    icon: <FileTextOutlined />,
                    label: 'Vanna Knowledge',
                },
            ],
        },
        {
            key: 'data-setup',
            icon: <DatabaseOutlined />,
            label: 'Data Setup',
            children: [
                {
                    key: '/analyzer',
                    icon: <RobotOutlined />,
                    label: 'Schema Analyzer',
                },
                {
                    key: '/schema',
                    icon: <TableOutlined />,
                    label: 'Schema Explorer',
                },
                {
                    key: '/contexts',
                    icon: <DatabaseOutlined />,
                    label: 'Data Contexts',
                },
                {
                    key: '/context-onboarding',
                    icon: <RocketOutlined />,
                    label: 'Context Onboarding',
                },
                {
                    key: '/view-builder',
                    icon: <BuildOutlined />,
                    label: 'View Builder',
                },
                {
                    key: '/view-manager',
                    icon: <SwapOutlined />,
                    label: 'View Manager',
                },
                {
                    key: '/dimension-families',
                    icon: <ApartmentOutlined />,
                    label: 'Dimension Families',
                },
                {
                    key: '/hierarchy',
                    icon: <ApartmentOutlined />,
                    label: 'Master Data',
                },
                {
                    key: '/rules',
                    icon: <SafetyCertificateOutlined />,
                    label: 'Business Rules',
                },
                {
                    key: '/mappings',
                    icon: <ProjectOutlined />,
                    label: 'Semantic Mappings',
                },
                {
                    key: '/examples',
                    icon: <BulbOutlined />,
                    label: 'Golden Examples',
                },
            ],
        },
        {
            key: 'monitoring',
            icon: <WarningOutlined />,
            label: 'Monitoring',
            children: [
                {
                    key: '/feedback',
                    icon: <MessageOutlined />,
                    label: 'Feedback',
                },
                {
                    key: '/query-logs',
                    icon: <FileSearchOutlined />,
                    label: 'Query Logs',
                },
                {
                    key: '/data-warnings',
                    icon: <WarningOutlined />,
                    label: 'Data Warnings',
                },
                {
                    key: '/query-patterns',
                    icon: <ForkOutlined />,
                    label: 'Query Patterns',
                },
            ],
        },
        {
            key: 'system',
            icon: <SettingOutlined />,
            label: 'System',
            children: [
                {
                    key: '/users',
                    icon: <UserOutlined />,
                    label: 'User Management',
                },
            ],
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

    const currentMeta = routeMeta[location.pathname] || { title: 'Admin', section: 'Workspace' };
    const showSectionLabel = currentMeta.section && currentMeta.section !== currentMeta.title;

    useEffect(() => {
        const nextOpenKeys = Array.from(new Set([
            ...readStoredOpenKeys(),
            ...(routeParents[location.pathname] || []),
        ]));
        setOpenKeys(nextOpenKeys);
        persistOpenKeys(nextOpenKeys);

        contentScrollRef.current?.scrollTo({ top: 0, left: 0, behavior: 'auto' });

        const activeMenuItem = menuScrollRef.current?.querySelector(
            `[data-menu-id="${location.pathname}"]`
        ) as HTMLElement | null;
        activeMenuItem?.scrollIntoView({ block: 'nearest' });
    }, [location.pathname]);

    const handleOpenChange = (keys: string[]) => {
        setOpenKeys(keys);
        persistOpenKeys(keys);
    };

    return (
        <Layout style={{ minHeight: '100vh', height: '100vh', overflow: 'hidden', background: '#eef2f6' }}>
            <Sider
                trigger={null}
                collapsible
                collapsed={collapsed}
                width={288}
                collapsedWidth={88}
                style={{
                    background: '#f7f8fa',
                    borderRight: '1px solid #e5e7eb',
                    height: '100vh',
                    overflow: 'hidden',
                }}
            >
                <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                    <div style={{ padding: collapsed ? '16px 12px' : '20px 20px 12px' }}>
                        <div style={{
                            borderRadius: 16,
                            padding: collapsed ? '16px 8px' : '16px 16px 14px',
                            background: 'linear-gradient(180deg, #ffffff 0%, #f3f5f8 100%)',
                            border: '1px solid #e5e7eb',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'space-between' }}>
                                <div>
                                    <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.8 }}>NT Admin</div>
                                    {!collapsed && <div style={{ fontWeight: 700, color: '#111827' }}>AI Assistant</div>}
                                </div>
                                {!collapsed && <Tag color="blue">Ops</Tag>}
                            </div>
                            {!collapsed && (
                                <Text style={{ display: 'block', marginTop: 10, color: '#4b5563' }}>
                                    Configure providers, maintain data context, and watch query quality from one workspace.
                                </Text>
                            )}
                        </div>
                    </div>

                    <div ref={menuScrollRef} style={{ flex: 1, overflowY: 'auto', padding: collapsed ? '0 8px 16px' : '0 12px 16px' }}>
                        <Menu
                            mode="inline"
                            selectedKeys={[location.pathname]}
                            openKeys={collapsed ? [] : openKeys}
                            items={menuItems}
                            onOpenChange={handleOpenChange}
                            onClick={({ key }) => navigate(key)}
                            style={{
                                background: 'transparent',
                                borderInlineEnd: 'none',
                            }}
                        />
                    </div>

                    {!collapsed && (
                        <div style={{ padding: '0 20px 20px' }}>
                            <div style={{
                                borderRadius: 14,
                                border: '1px solid #e5e7eb',
                                background: '#ffffff',
                                padding: '12px 14px',
                            }}>
                                <Text style={{ display: 'block', color: '#6b7280', fontSize: 12 }}>Signed in as</Text>
                                <Text strong>{user?.display_name || 'Admin'}</Text>
                            </div>
                        </div>
                    )}
                </div>
            </Sider>
            <Layout style={{ background: 'transparent' }}>
                <Header style={{
                    padding: '0 16px 0 0',
                    background: colorBgContainer,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    borderBottom: '1px solid #e5e7eb',
                    minHeight: 64,
                    lineHeight: 'normal',
                }}>
                    <Space size={12} align="center" style={{ minWidth: 0 }}>
                        <Button
                            type="text"
                            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                            onClick={() => setCollapsed(!collapsed)}
                            style={{
                                fontSize: '16px',
                                width: 48,
                                height: 48,
                                flex: '0 0 auto',
                            }}
                        />
                        <div style={{ minWidth: 0, padding: '8px 0' }}>
                            {showSectionLabel ? (
                                <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 2 }}>
                                    {currentMeta.section}
                                </div>
                            ) : null}
                            <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {currentMeta.title}
                            </div>
                        </div>
                    </Space>

                    <Dropdown menu={userMenu}>
                        <Space style={{ cursor: 'pointer', flex: '0 0 auto' }}>
                            <Avatar icon={<UserOutlined />} />
                            <span>{user?.display_name || 'Admin'}</span>
                        </Space>
                    </Dropdown>
                </Header>

                <div ref={contentScrollRef} style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
                    <Content
                        style={{
                            padding: '24px clamp(16px, 3vw, 28px)',
                            minHeight: 'calc(100vh - 96px)',
                            background: colorBgContainer,
                            borderRadius: borderRadiusLG,
                            maxWidth: '100%',
                            boxShadow: '0 20px 60px rgba(15, 23, 42, 0.06)',
                        }}
                    >
                        <Outlet />
                    </Content>
                </div>
            </Layout>
        </Layout>
    );
};

export default AppLayout;
