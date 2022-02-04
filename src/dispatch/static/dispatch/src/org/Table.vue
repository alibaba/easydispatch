<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-card flat style="z-index: 2;">
      <v-card-text>
        <v-container grid-list-md>
          <v-layout wrap>
            <v-flex xs12>
              <span class="subtitle-1">Organization Settings</span>
              <div style=" float:right;">
                <v-btn
                  icon
                  color="primary"
                  :loading="loading"
                  :disabled="invalid || !validated ||!userInfo || userInfo.role=='User'"
                  @click="onSave()"
                >
                  <v-icon>save</v-icon>
                </v-btn>
                <v-btn
                  icon
                  color="red"
                  @click="removeShow()"
                  :disabled="!userInfo || userInfo.role=='User' "
                >
                  <v-icon>delete</v-icon>
                </v-btn>
              </div>
            </v-flex>

            <v-flex xs12>
              <v-row no-gutters>
                <v-col cols="12" sm="3" class="d-flex align-center">
                  <ValidationProvider name="OrganizationCode" rules="required" immediate>
                    <v-text-field
                      v-model="code"
                      slot-scope="{ errors, valid }"
                      label="Code"
                      :error-messages="errors"
                      :success="valid"
                      hint="The unique key for the org."
                      required
                      :disabled="true"
                    />
                  </ValidationProvider>
                </v-col>
                <v-col cols="12" sm="9">
                  <v-text-field
                    v-model="callback_url"
                    label="Callback Url"
                    hint="The url for the org. for Send data to a third party"
                    clearable
                    required
                    :disabled="!userInfo || userInfo.role=='User' "
                  />
                </v-col>
                <!-- zulip -->
                <v-col cols="12" md="3">
                  <v-switch
                    v-model="zulip_is_active"
                    hint="zulip is_active for your org."
                    label="Use Zulip"
                  />
                </v-col>
                <v-col cols="12" md="9">
                  <v-text-field v-model="zulip_site" label="zulip server website" required></v-text-field>
                </v-col>

                <v-col cols="12" md="6">
                  <v-text-field v-model="zulip_user_name" label="zulip bot username" required></v-text-field>
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    autocomplete="new-password"
                    v-model="zulip_password"
                    :type="'password'"
                    label="zulip bot api key"
                    required
                  ></v-text-field>
                </v-col>
                <!-- zulip -->

                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="job_count_statistics"
                    label="Jobs Limit (available/total)"
                    required
                    disabled
                  ></v-text-field>
                </v-col>

                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="worker_count_statistics"
                    label="Workers Limit (available/total)"
                    required
                    disabled
                  ></v-text-field>
                </v-col>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model="team_count_statistics"
                    label="Teams Limit (available/total)"
                    required
                    disabled
                  ></v-text-field>
                </v-col>
              </v-row>
              <v-row no-gutters>
                <v-col cols="12" sm="12">
                  <span class="subtitle-2">team_flex_form_schema</span>
                  <vue-json-editor
                    v-model="team_flex_form_schema"
                    :mode="'code'"
                    :show-btns="false"
                    :expandedOnStart="true"
                    @json-change="onJsonChange"
                    class="vue_json_editor_context"
                  ></vue-json-editor>
                </v-col>
              </v-row>
              <v-row no-gutters>
                <v-col cols="12" sm="12">
                  <span class="subtitle-2">job_flex_form_schema</span>
                  <vue-json-editor
                    v-model="job_flex_form_schema"
                    :mode="'code'"
                    :show-btns="false"
                    :expandedOnStart="true"
                    @json-change="onJsonChange"
                    class="vue_json_editor_context"
                  ></vue-json-editor>
                </v-col>
              </v-row>
              <v-row no-gutters>
                <v-col cols="12" sm="12">
                  <span class="subtitle-2">worker_flex_form_schema</span>
                  <vue-json-editor
                    v-model="worker_flex_form_schema"
                    :mode="'code'"
                    :show-btns="false"
                    :expandedOnStart="true"
                    @json-change="onJsonChange"
                    class="vue_json_editor_context"
                  ></vue-json-editor>
                </v-col>
              </v-row>
            </v-flex>
          </v-layout>
        </v-container>
      </v-card-text>
      <OrgDeleteDialog />
    </v-card>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import { mapState } from "vuex";

import OrgDeleteDialog from "@/org/DeleteDialog.vue";
import vueJsonEditor from "vue-json-editor";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "OrgFromEditSheet",
  components: {
    ValidationObserver,
    ValidationProvider,
    vueJsonEditor,
    OrgDeleteDialog,
  },
  computed: {
    ...mapFields("org", [
      "selected.id",
      "selected.code",
      "selected.callback_url",
      "selected.worker_flex_form_schema",
      "selected.team_flex_form_schema",
      "selected.job_flex_form_schema",
      "selected.max_nbr_workers",
      "selected.max_nbr_teams",
      "selected.max_nbr_jobs",
      "selected.worker_count",
      "selected.team_count",
      "selected.job_count",
      "selected.zulip_is_active",
      "selected.zulip_site",
      "selected.zulip_user_name",
      "selected.zulip_password",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
    ...mapState("auth", ["userInfo"]),
    worker_count_statistics() {
      return this.worker_count + "/" + this.max_nbr_workers;
    },
    job_count_statistics() {
      return this.job_count + "/" + this.max_nbr_jobs;
    },
    team_count_statistics() {
      return this.team_count + "/" + this.max_nbr_teams;
    },
  },
  mounted() {
    this.getOrg();
  },
  methods: {
    ...mapActions("org", ["save", "getOrg", "removeShow"]),
    ...mapActions("auth", ["logout"]),
    onJsonChange(value) {
      console.log("value:", value);
    },
    onSave() {
      this.save();
      let that = this;
      setTimeout(function () {
        if (that.userInfo.org_code != that.code) {
          that.logout();
        }
      }, 500);
    },
  },
};
</script>
<style  >
.jsoneditor-vue {
  height: 100%;
}
.vue_json_editor_context {
  height: calc(100vh - 430px);
}
.jsoneditor-poweredBy {
  display: none;
}
</style>
