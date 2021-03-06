import Vue from 'vue'
import App from './App.vue'
import vuetify from './vuetify/'
import router from './router/'
import store from './store'
import filters from './filters' // eslint-disable-line no-unused-vars
import './registerServiceWorker'
import 'roboto-fontface/css/roboto/roboto-fontface.css'
import 'font-awesome/css/font-awesome.css'
import 'material-design-icons-iconfont/dist/material-design-icons.css'

import * as Sentry from '@sentry/browser'
import * as Integrations from '@sentry/integrations'

if (process.env.VUE_APP_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.VUE_APP_SENTRY_DSN,
    integrations: [new Integrations.Vue({ Vue, attachProps: true })]
  })
}

Vue.config.productionTip = false
new Vue({
  vuetify,
  router,
  store,
  render: h => h(App)
}).$mount('#app')
