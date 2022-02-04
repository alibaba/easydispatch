<template>
  <ValidationObserver v-slot="{ invalid, validated }">
    <v-navigation-drawer v-model="showCreateEdit" app clipped right width="500">
      <template v-slot:prepend>
        <v-list-item two-line>
          <v-list-item-content>
            <v-list-item-title v-if="id" class="title">Edit</v-list-item-title>
            <v-list-item-title v-else class="title">New</v-list-item-title>
            <v-list-item-subtitle>Item</v-list-item-subtitle>
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
        <v-tab key="item">Item Detail</v-tab>
        <v-tab key="flex_form" v-if="flexFormSchema!=null">Flex Form</v-tab>
      </v-tabs>
      <v-tabs-items v-model="tab">
        <v-tab-item key="item">
          <v-card flat>
            <v-card-text>
              <v-container grid-list-md>
                <v-layout wrap>
                  <v-flex xs12>
                    <span class="subtitle-2">Item Details</span>
                  </v-flex>
                  <v-flex xs6>
                    <ValidationProvider name="Code" rules="required" immediate>
                      <v-text-field
                        v-model="code"
                        slot-scope="{ errors, valid }"
                        label="Code"
                        :error-messages="errors"
                        :success="valid"
                        hint="The unique key for the item."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>
                  <v-flex xs6>
                    <ValidationProvider name="Name" rules="required" immediate>
                      <v-text-field
                        v-model="name"
                        slot-scope="{ errors, valid }"
                        :error-messages="errors"
                        :success="valid"
                        label="Name"
                        hint="A name for your item."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>

                  <v-flex xs6>
                    <ValidationProvider name="Volume" rules="required" immediate>
                      <v-text-field
                        v-model="volume"
                        slot-scope="{ errors, valid }"
                        :error-messages="errors"
                        :success="valid"
                        label="Volume"
                        type="number"
                        hint="A Volume for your depot."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>

                  <v-flex xs6>
                    <ValidationProvider name="weight" rules="required" immediate>
                      <v-text-field
                        v-model="weight"
                        slot-scope="{ errors, valid }"
                        :error-messages="errors"
                        :success="valid"
                        label="weight"
                        type="number"
                        hint="A weight for your depot."
                        clearable
                        required
                      />
                    </ValidationProvider>
                  </v-flex>

                  <v-flex xs12>
                    <v-textarea
                      v-model="description"
                      label="Description"
                      hint="Description of depot."
                      clearable
                    />
                  </v-flex>
                  <v-flex xs12>
                    <v-switch
                      v-model="is_active"
                      hint="A is_active for your depot."
                      label="is_active"
                    />
                  </v-flex>
                </v-layout>
              </v-container>
            </v-card-text>
          </v-card>
        </v-tab-item>
        <v-tab-item key="flex_form">
          <ItemFlexForm :formData="localFlexFormData" :formSchema="flexFormSchema" />
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
import ItemFlexForm from "@/components/FlexForm.vue";
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
    ItemFlexForm,
  },
  data() {
    return {
      tab: null,
      flexFormSchema: null,
    };
  },
  computed: {
    ...mapFields("item", [
      "selected.id",
      "selected.code",
      "selected.name",
      "selected.description",
      "selected.weight",
      "selected.volume",
      "selected.flex_form_data",
      "selected.is_active",
      "selected.loading",
      "dialogs.showCreateEdit",
    ]),
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
    ...mapActions("item", [
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
