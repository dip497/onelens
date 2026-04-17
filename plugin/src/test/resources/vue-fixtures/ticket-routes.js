import config from './config'

const routePrefix = config.routePrefix
const moduleName = config.name
const routeNamePrefix = config.routeNamePrefix

export default [
  {
    path: `/${routePrefix}/:ticketType`,
    component: () => import('./views/main.vue'),
    meta: { moduleName },
    children: [
      { path: '', name: `${routeNamePrefix}`, component: () => import('./views/list-view.vue') },
      { path: 'create', name: `${routeNamePrefix}.create`, component: () => import('./views/create.vue') },
      { path: ':id', name: `${routeNamePrefix}.view`, component: () => import('./views/view.vue') }
    ]
  }
]
