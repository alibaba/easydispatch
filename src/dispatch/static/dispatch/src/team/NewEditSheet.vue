<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Team</v-list-item-subtitle>
          </v-list-item-content>
          <v-btn
            icon
            color="primary"
            :loading="loading"
            :disabled="invalid || !validated"
            @click="submitSaveLocal()"
          >
            <v-icon>save</v-icon>
          </v-btn>
          <v-btn icon color="secondary" @click="closeCreateEdit()">
            <v-icon>close</v-icon>
          </v-btn>
        </v-list-item>
      </template>
      <v-tabs fixed-tabs v-model="tab">
        <v-tab key="team">Team Detail</v-tab>
        <v-tab key="flex_form">Flex Form</v-tab>
      </v-tabs>
      <v-tabs-items v-model="tab">
        <v-tab-item key="team">
          <v-card flat>
            <v-card-text>
              <v-container grid-list-md>
                <v-layout wrap>
                  <v-flex xs12>
                    <span class="subtitle-2">Team Details</span>
                  </v-flex>
                  <v-flex xs12>
                    <ValidationProvider name="TeamCode" rules="required" immediate>
                      <v-text-field
                        v-model="code"
                        slot-scope="{ errors, valid }"
                        label="Code"
                        :error-messages="errors"
                        :success="valid"
                        hint="The unique key for the team."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>
                  <v-flex xs12>
                    <ValidationProvider name="Name" rules="required" immediate>
                      <v-text-field
                        v-model="name"
                        slot-scope="{ errors, valid }"
                        :error-messages="errors"
                        :success="valid"
                        label="Name"
                        hint="A name for your team."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>
                  <v-flex xs12>
                    <ServiceSelect v-model="planner_service" rules="required" />
                  </v-flex>
                </v-layout>
              </v-container>
            </v-card-text>
          </v-card>
        </v-tab-item>
        <v-tab-item key="flex_form">
          <TeamFlexForm :formData="localFlexFormData" :formSchema="dataFormSchema" />
        </v-tab-item>
      </v-tabs-items>
    </v-navigation-drawer>
  </ValidationObserver>
</template>

<script>
import { mapFields } from "vuex-map-fields";
import { mapActions } from "vuex";
import { ValidationObserver, ValidationProvider, extend } from "vee-validate";
import { required } from "vee-validate/dist/rules";
import ServiceSelect from "@/service/ServiceSelect.vue";
import TeamFlexForm from "@/components/FlexForm.vue";
import { cloneDeep } from "lodash";
extend("required", {
  ...required,
  message: "This field is required",
});

export default {
  name: "ServiceNewEditSheet",

  components: {
    ValidationObserver,
    ValidationProvider,
    ServiceSelect,
    TeamFlexForm,
  },
  data() {
    let today = new Date();
    let env_start_day = today.toISOString().split("T")[0].replace(/-/g, "");
    return {
      tab: null,
    };
  },
  computed: {
    ...mapFields("team", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.description",
      "selected.planner_service",
      "selected.flex_form_data",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
    ...mapFields("org", ["selected.team_flex_form_schema"]),
    // 计算属性的 getter
    dataFormSchema: function () {
      return JSON.parse(JSON.stringify(this.team_flex_form_schema));
    },
    localFlexFormData: {
      get() {
        return cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data)));
      },
      set(value) {
        this.$emit("input", value);
      },
    },
  },

  methods: {
    ...mapActions("team", [
      "save",
      "closeCreateEdit",
      "setSelectedFormDataAndSave",
    ]),
    submitSaveLocal() {
      this.setSelectedFormDataAndSave({
        flex_form_data: Object.assign(
          cloneDeep(JSON.parse(JSON.stringify(this.flex_form_data))),
          this.localFlexFormData
        ),
      });
    },
  },
};
</script>
